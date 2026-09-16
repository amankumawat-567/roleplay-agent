from langchain_core.tools import BaseTool, tool

from roleplay_agent.agents.research.browser import fetch_snippets
from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.skills.registry import register

# A turn's tool observation feeds straight back into the model's next
# reasoning step (unlike the one-shot research pipeline, which has its own
# dedicated summarization pass) - cap it so one search can't blow the
# context budget.
_MAX_OBSERVATION_CHARS = 4000

SKILL_ID = "web_research"


def build_web_research_tool(settings: Settings, app_config: AppConfig) -> BaseTool:
    # The tool's own name (from this function's name) must match SKILL_ID -
    # agent.py's routing checks a requested tool_call's name against
    # Game.skills (the skill id), not against a separate display name.
    @tool
    def web_research(query: str) -> str:
        """Search the web for current facts, references, or details you
        don't already know, so you can answer accurately without breaking
        character. Returns a few short snippets from real pages."""
        snippets = fetch_snippets(query, app_config.research_user_agent, app_config.research_max_results)
        if not snippets:
            return "No results found."
        joined = "\n\n---\n\n".join(f"{s['url']}\n{s['text']}" for s in snippets)
        return joined[:_MAX_OBSERVATION_CHARS]

    return web_research


register(SKILL_ID, build_web_research_tool)
