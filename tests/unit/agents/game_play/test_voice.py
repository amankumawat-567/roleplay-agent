from roleplay_agent.agents.game_play import voice as voice_module
from roleplay_agent.agents.game_play.voice import SpeechSegment, VoiceTurn, generate_voice_turn
from roleplay_agent.services.storage.models import Message


class _FakeStructuredLLM:
    def __init__(self, turn: VoiceTurn):
        self.turn = turn
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.turn


class _FakeLLM:
    def __init__(self, turn: VoiceTurn):
        self.turn = turn
        self.structured: _FakeStructuredLLM | None = None

    def with_structured_output(self, schema):
        assert schema is VoiceTurn
        self.structured = _FakeStructuredLLM(self.turn)
        return self.structured


def test_generate_voice_turn_returns_structured_output(monkeypatch):
    turn = VoiceTurn(
        user_said="hey what's up",
        segments=[SpeechSegment(text="Hey there.", delivery="warm, a little surprised")],
    )
    fake = _FakeLLM(turn)
    monkeypatch.setattr(voice_module, "build_llm", lambda *a, **k: fake)

    result = generate_voice_turn(
        "system prompt",
        [Message(role="user", content="hi")],
        b"RIFF....WAVEfmt ",
        "ollama",
        "test-model",
        8192,
        "30m",
    )

    assert result == turn
    messages = fake.structured.calls[0]
    assert messages[0].content == "system prompt"
    assert messages[1].content == "hi"
    # The current turn's audio is appended after prior-turn text history,
    # as an image_url-shaped content block (see agent.context.to_audio_message).
    audio_block = messages[-1].content[0]
    assert audio_block["type"] == "image_url"
    assert audio_block["image_url"].startswith("data:audio/wav;base64,")


def test_generate_voice_turn_uses_provider_and_model(monkeypatch):
    calls = []
    turn = VoiceTurn(user_said="ok", segments=[SpeechSegment(text="ok")])
    fake = _FakeLLM(turn)
    monkeypatch.setattr(
        voice_module,
        "build_llm",
        lambda provider, model, num_ctx, keep_alive: calls.append((provider, model, num_ctx, keep_alive)) or fake,
    )

    generate_voice_turn("sys", [], b"wav-bytes", "openai", "gpt-4o-mini", 4096, "5m")

    assert calls == [("openai", "gpt-4o-mini", 4096, "5m")]


def test_speech_segment_delivery_defaults_to_none():
    segment = SpeechSegment(text="Just saying it plain.")
    assert segment.delivery is None


def test_voice_turn_requires_at_least_the_segments_field():
    turn = VoiceTurn(
        user_said="two lines please",
        segments=[SpeechSegment(text="a"), SpeechSegment(text="b", delivery="quieter")],
    )
    assert len(turn.segments) == 2
    assert turn.segments[1].delivery == "quieter"
