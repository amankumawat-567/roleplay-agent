# Adding a skill

A "skill" is a mid-conversation tool the model can call - `agent/agent.py`'s
loop binds whichever skills a persona's `game.yaml` authorizes and routes a
matching tool call to a shared `ToolNode`, looping `generate -> ToolNode ->
generate` until the model stops calling tools. See `docs/ARCHITECTURE.md`'s
"Skills: an agentic tool-calling loop" for the design rationale; this doc is
just the mechanics of adding one.

There are two today: `src/roleplay_agent/skills/web_research.py` and
`skills/schedule_followup.py`. Use whichever is closer to what you're
building as a template.

## The mechanism

`skills/registry.py` maps a skill id to a factory function:

```python
ToolFactory = Callable[[Settings, AppConfig], BaseTool]
```

A skill module builds a `BaseTool` (a `@tool`-decorated function) and
registers it under a skill id at import time:

```python
SKILL_ID = "my_skill"

def build_my_skill_tool(settings: Settings, app_config: AppConfig) -> BaseTool:
    @tool
    def my_skill(query: str) -> str:
        """Docstring the model reads to decide when/how to call this."""
        ...
        return "some observation string"

    return my_skill

register(SKILL_ID, build_my_skill_tool)
```

The factory gets both config objects (see `docs/ARCHITECTURE.md`'s "Config
hygiene") and takes whichever half it actually needs - `schedule_followup`
needs `Settings.db_path`, `web_research` needs `AppConfig`'s research
fields. `api/dependencies.py`'s `get_skill_tools` calls `build_tools(...)`
once per process (cached, shared across every session), so a skill's
factory should build cheap, stateless-enough objects (e.g. a fresh
repository wrapping the shared `Database`), not open a connection meant to
live for one call only.

**The module has to actually run for `register(...)` to fire.**
`skills/__init__.py` is the one place that imports every skill module for
its side effect:

```python
from . import schedule_followup, web_research  # noqa: F401 - importing registers their tools
```

Add your new module to that same import line, or `register(...)` never
runs and `GET /api/skills` simply won't list it.

## The invariant: tool name == skill id

`registry.build_tools` raises if a registered tool's own `.name` (derived
from the `@tool`-decorated function's name) doesn't match the `skill_id` it
was registered under:

```python
if tool.name != skill_id:
    raise ValueError(f"Skill '{skill_id}' registered a tool named '{tool.name}' - they must match.")
```

This isn't defensive paranoia - it caught a real bug: a skill registered as
`"web_research"` whose `@tool` function was named `web_search`. `agent.py`'s
tool-call routing authorizes a request by comparing the model's
`tool_call["name"]` directly against a game's `skills` list (skill ids), so
a mismatch meant every call to that tool was silently rejected as
unauthorized. Keep `SKILL_ID` and the `@tool` function's name identical, or
this raises loudly at startup instead of failing silently at chat time.

## Reading state the model shouldn't supply

`schedule_followup` needs the current `session_id`, but the model has no
business inventing one. It's pulled off the live LangGraph state instead of
being a model-supplied argument:

```python
@tool
def schedule_followup(
    minutes: float, reason: str, session_id: Annotated[str, InjectedState("session_id")]
) -> str:
    ...
```

`InjectedState(...)` args are automatically excluded from the schema the
model sees, and only resolve inside a real compiled-graph run - use the same
pattern for anything else a tool needs that comes from app state rather
than the model's own reasoning.

## Opting a persona in

Add the skill id to a `game.yaml`'s `skills` list:

```yaml
skills: [web_research]
```

Empty (or omitted) behaves exactly like no tool-calling at all. In the
editor UI, `GameEditorPage`'s skills field is a live search-and-add picker
backed by `GET /api/skills` - a newly-registered skill needs no frontend
change to show up there.

## Keep the observation small

A tool's return value feeds straight back into the model's next reasoning
step, unlike the one-shot research pipeline's own summarization pass -
`web_research` caps its observation at 4000 characters
(`_MAX_OBSERVATION_CHARS`) so one call can't blow the context budget. Do the
same for anything that could return an unbounded amount of text.
