from roleplay_agent.components.memory import summarizer as summarizer_module
from roleplay_agent.services.storage.models import Message


class _FakeReply:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        return _FakeReply(self.reply)


def test_build_summarizer_threads_provider_and_model_through(monkeypatch):
    calls = []

    def fake_build_llm(provider, model, num_ctx, keep_alive):
        calls.append((provider, model, num_ctx, keep_alive))
        return _FakeLLM("  a summary  ")

    monkeypatch.setattr(summarizer_module, "build_llm", fake_build_llm)

    summarize = summarizer_module.build_summarizer("openai", "gpt-4o-mini", 8192, "30m")
    result = summarize("", [Message(role="user", content="hi")])

    assert result == "a summary"
    assert calls == [("openai", "gpt-4o-mini", 8192, "30m")]
