import asyncio
from dataclasses import dataclass

import pytest

from roleplay_agent.agents.game_builder import builder as game_builder_module
from roleplay_agent.config.settings import AppConfig
from roleplay_agent.schema.game_builder import BuilderMessage, GameDraft


@dataclass
class _Chunk:
    content: str


class _FakeStructuredLLM:
    def __init__(self, draft: GameDraft):
        self.draft = draft
        self.calls: list[str] = []

    def invoke(self, prompt: str) -> GameDraft:
        self.calls.append(prompt)
        return self.draft


class _FakeLLM:
    def __init__(self, draft: GameDraft | None = None, stream_chunks: list[str] | None = None):
        self.draft = draft
        self.stream_chunks = stream_chunks or []
        self.structured: _FakeStructuredLLM | None = None
        self.streamed_messages = None

    def with_structured_output(self, schema):
        assert schema is GameDraft
        self.structured = _FakeStructuredLLM(self.draft)
        return self.structured

    async def astream(self, messages):
        self.streamed_messages = messages
        for content in self.stream_chunks:
            yield _Chunk(content)


def _app_config(**overrides) -> AppConfig:
    return AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
        **overrides,
    )


def test_stream_builder_reply_yields_streamed_content(monkeypatch):
    fake = _FakeLLM(stream_chunks=["Hello", "", " there"])
    monkeypatch.setattr(game_builder_module, "build_llm", lambda *a, **k: fake)

    async def collect():
        pieces = []
        async for piece in game_builder_module.stream_builder_reply(
            [BuilderMessage(role="user", content="hi")], _app_config()
        ):
            pieces.append(piece)
        return pieces

    pieces = asyncio.run(collect())

    assert pieces == ["Hello", " there"]  # the empty chunk is skipped


def test_stream_builder_reply_includes_system_prompt_and_history(monkeypatch):
    fake = _FakeLLM(stream_chunks=["ok"])
    monkeypatch.setattr(game_builder_module, "build_llm", lambda *a, **k: fake)

    async def collect():
        async for _ in game_builder_module.stream_builder_reply(
            [BuilderMessage(role="user", content="I want a wizard")], _app_config()
        ):
            pass

    asyncio.run(collect())

    lc_messages = fake.streamed_messages
    assert lc_messages[0].content == game_builder_module.BUILDER_SYSTEM_PROMPT
    assert lc_messages[1].content == "I want a wizard"


def test_stream_builder_reply_uses_builder_provider_and_model(monkeypatch):
    calls = []
    fake = _FakeLLM(stream_chunks=[])

    def fake_build_llm(provider, model, num_ctx, keep_alive, reasoning=None):
        calls.append((provider, model, num_ctx, keep_alive))
        return fake

    monkeypatch.setattr(game_builder_module, "build_llm", fake_build_llm)
    app_config = _app_config(builder_provider="openai", builder_model="gpt-4o-mini")

    async def collect():
        async for _ in game_builder_module.stream_builder_reply([], app_config):
            pass

    asyncio.run(collect())

    assert calls == [("openai", "gpt-4o-mini", app_config.default_num_ctx, app_config.keep_alive)]


def test_generate_draft_returns_structured_output(monkeypatch):
    draft = GameDraft(title="A Title", persona="p", user_role="u", script="s")
    fake = _FakeLLM(draft=draft)
    monkeypatch.setattr(game_builder_module, "build_llm", lambda *a, **k: fake)

    result = game_builder_module.generate_draft(
        [BuilderMessage(role="user", content="I want a wizard")], _app_config()
    )

    assert result == draft
    assert "I want a wizard" in fake.structured.calls[0]


def test_generate_draft_from_transcript_returns_structured_output(monkeypatch):
    draft = GameDraft(title="A Title", persona="p", user_role="u", script="s")
    fake = _FakeLLM(draft=draft)
    monkeypatch.setattr(game_builder_module, "build_llm", lambda *a, **k: fake)

    result = game_builder_module.generate_draft_from_transcript("welcome to my video about wizards", _app_config())

    assert result == draft
    assert "welcome to my video about wizards" in fake.structured.calls[0]


def test_generate_draft_propagates_provider_errors(monkeypatch):
    from roleplay_agent.services.llm.providers import ProviderConfigError

    def raise_error(*a, **k):
        raise ProviderConfigError("Set OPENAI_API_KEY")

    monkeypatch.setattr(game_builder_module, "build_llm", raise_error)

    with pytest.raises(ProviderConfigError):
        game_builder_module.generate_draft([BuilderMessage(role="user", content="hi")], _app_config())
