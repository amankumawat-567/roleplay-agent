from collections.abc import Callable

from langchain_core.tools import BaseTool

from roleplay_agent.config.settings import AppConfig, Settings

# A factory gets both objects (docs/ARCHITECTURE.md's "Config hygiene"
# split them in two) since different skills need different halves -
# schedule_followup needs Settings.db_path (infra/where data lives),
# web_research needs AppConfig's research fields (app behavior) - and
# takes whichever it actually needs, ignoring the other.
ToolFactory = Callable[[Settings, AppConfig], BaseTool]

_FACTORIES: dict[str, ToolFactory] = {}


def register(skill_id: str, factory: ToolFactory) -> None:
    _FACTORIES[skill_id] = factory


def known_skill_ids() -> list[str]:
    return list(_FACTORIES)


def build_tools(settings: Settings, app_config: AppConfig) -> dict[str, BaseTool]:
    """One instance of every registered skill's tool, keyed by skill id -
    built once (see api/dependencies.get_skill_tools) and shared; a game's
    Game.skills list then just selects a subset per turn (agent/agent.py's
    _generate binds only those to the model)."""
    tools = {skill_id: factory(settings, app_config) for skill_id, factory in _FACTORIES.items()}
    for skill_id, tool in tools.items():
        # agent.py's tool-call routing authorizes a request by comparing
        # its tool_call["name"] against Game.skills (skill ids) directly -
        # a skill whose tool.name differs from its own id would have every
        # one of its calls silently rejected as "unauthorized" (a real bug
        # this caught: the skill was registered as "web_research" but its
        # @tool-decorated function was named web_search).
        if tool.name != skill_id:
            raise ValueError(f"Skill '{skill_id}' registered a tool named '{tool.name}' - they must match.")
    return tools
