import pytest

from roleplay_agent.agents.research import summarizer as summarizer_module
from roleplay_agent.services.llm.providers import ProviderConfigError


class _FakeReply:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        return _FakeReply(self.reply)


def test_summarize_style_threads_provider_and_model_through(monkeypatch):
    calls = []

    def fake_build_llm(provider, model, num_ctx, keep_alive):
        calls.append((provider, model, num_ctx, keep_alive))
        return _FakeLLM("  style notes  ")

    monkeypatch.setattr(summarizer_module, "build_llm", fake_build_llm)

    result = summarizer_module.summarize_style(
        "A friendly persona", [{"text": "scraped text", "url": "http://x"}], "anthropic", "claude-3-5", 8192, "30m"
    )

    assert result == "style notes"
    assert calls == [("anthropic", "claude-3-5", 8192, "30m")]


def test_summarize_style_empty_snippets_skips_the_llm_call(monkeypatch):
    def fail_build_llm(*args, **kwargs):
        raise AssertionError("build_llm should not be called with no snippets")

    monkeypatch.setattr(summarizer_module, "build_llm", fail_build_llm)

    assert summarizer_module.summarize_style("persona", [], "ollama", "llama3.1", 8192, "30m") == ""


def test_summarize_style_raises_clear_error_for_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        summarizer_module.summarize_style(
            "persona", [{"text": "text", "url": "http://x"}], "openai", "gpt-4o-mini", 8192, "30m"
        )
