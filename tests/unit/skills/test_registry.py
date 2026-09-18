import pytest
from langchain_core.tools import tool

from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.skills import registry


def _app_config() -> AppConfig:
    return AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
    )


def test_web_research_is_registered_on_import():
    # Importing roleplay_agent.skills (done by conftest/app startup) is
    # what registers "web_research" - this just confirms that side effect
    # actually happened, not re-registering it here.
    assert "web_research" in registry.known_skill_ids()


def test_build_tools_returns_one_tool_per_registered_skill():
    tools = registry.build_tools(Settings(), _app_config())

    assert set(tools) == set(registry.known_skill_ids())
    for skill_id, t in tools.items():
        assert t.name == skill_id  # agent.py's routing depends on this


def test_build_tools_rejects_a_tool_name_mismatch(monkeypatch):
    # Regression test: agent.py authorizes a tool_call by comparing its
    # name against Game.skills (skill ids) directly, so a skill whose tool
    # is named differently from its own registered id would have every
    # call silently rejected as unauthorized - this is exactly the bug a
    # live end-to-end test caught (registered as "web_research", tool
    # named "web_search").
    @tool
    def mismatched_name(query: str) -> str:
        """A tool deliberately named differently from its skill id."""
        return "never called"

    monkeypatch.setitem(registry._FACTORIES, "my_skill", lambda settings, app_config: mismatched_name)

    with pytest.raises(ValueError, match="my_skill"):
        registry.build_tools(Settings(), _app_config())
