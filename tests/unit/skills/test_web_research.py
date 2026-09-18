from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.skills import web_research as web_research_module
from roleplay_agent.skills.web_research import build_web_research_tool


def _app_config(**overrides) -> AppConfig:
    return AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
        **overrides,
    )


def test_web_research_returns_joined_snippets(monkeypatch):
    monkeypatch.setattr(
        web_research_module,
        "fetch_snippets",
        lambda query, user_agent, max_results: [
            {"url": "http://a.example", "text": "info about " + query},
            {"url": "http://b.example", "text": "more info"},
        ],
    )
    tool = build_web_research_tool(Settings(), _app_config())

    result = tool.invoke({"query": "roleplay agents"})

    assert "http://a.example" in result
    assert "info about roleplay agents" in result
    assert "http://b.example" in result


def test_web_research_no_results_returns_clear_message(monkeypatch):
    monkeypatch.setattr(web_research_module, "fetch_snippets", lambda query, user_agent, max_results: [])
    tool = build_web_research_tool(Settings(), _app_config())

    assert tool.invoke({"query": "nothing"}) == "No results found."


def test_web_research_truncates_long_observations(monkeypatch):
    monkeypatch.setattr(
        web_research_module,
        "fetch_snippets",
        lambda query, user_agent, max_results: [{"url": "http://a.example", "text": "x" * 10000}],
    )
    tool = build_web_research_tool(Settings(), _app_config())

    result = tool.invoke({"query": "q"})

    assert len(result) == web_research_module._MAX_OBSERVATION_CHARS


def test_web_research_passes_settings_through(monkeypatch):
    calls = []
    monkeypatch.setattr(
        web_research_module,
        "fetch_snippets",
        lambda query, user_agent, max_results: calls.append((query, user_agent, max_results)) or [],
    )
    app_config = _app_config(research_user_agent="TestAgent/1.0", research_max_results=2)
    tool = build_web_research_tool(Settings(), app_config)

    tool.invoke({"query": "q"})

    assert calls == [("q", "TestAgent/1.0", 2)]
