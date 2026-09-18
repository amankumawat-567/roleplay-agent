import httpx
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from roleplay_agent.agents.game_play import agent as agent_module
from roleplay_agent.components.memory import summarizer as summarizer_module
from roleplay_agent.services import tts as tts_module
from roleplay_agent.services.tts import TtsError
from tests.helpers import write_game


def _fake_llm(*args, **kwargs):
    # GenericFakeChatModel is a real LangChain chat model, so it emits
    # genuine on_chat_model_stream events through astream_events - unlike a
    # hand-rolled stub, this actually exercises the streaming path the
    # endpoint relies on. A fresh instance per call so it's safe to reuse
    # for both the generate node and the background fold's summarizer.
    return GenericFakeChatModel(messages=iter([AIMessage(content="Hello there")]))


class _BindableFakeChatModel(GenericFakeChatModel):
    """GenericFakeChatModel.bind_tools raises NotImplementedError - _generate
    calls it whenever a game declares any skills, so this override is needed
    for a skills-enabled game to even reach a normal (non-tool-calling)
    reply in a test."""

    def bind_tools(self, tools, **kwargs):
        return self


class _FakeEmbeddings:
    """Stands in for OllamaEmbeddings - covers both the sync embed_query
    the background fold task uses and the async aembed_query agent._prepare
    uses, so it works as a drop-in for deps.get_embeddings in either path."""

    def __init__(self, vector=None):
        self.vector = vector or [1.0, 0.0]
        self.calls: list[str] = []

    def embed_query(self, text):
        self.calls.append(text)
        return self.vector

    async def aembed_query(self, text):
        self.calls.append(text)
        return self.vector


def test_chat_streams_reply_and_persists_messages(client, app_env, monkeypatch):
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert response.text == "Hello there"

    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "hi"),
        ("assistant", "Hello there"),
    ]


def test_chat_missing_session_returns_404(client, app_env):
    response = client.post("/api/sessions/does-not-exist/chat", json={"message": "hi"})
    assert response.status_code == 404


def test_chat_reports_clear_message_when_ollama_unreachable_mid_stream(client, app_env, monkeypatch):
    class _UnreachableLLM:
        async def ainvoke(self, messages):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: _UnreachableLLM())
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    # The HTTP status is already committed by the time a mid-stream error
    # happens, so it stays 200 - what matters is the body is a clear
    # message, not a traceback, and nothing gets persisted as if it were a
    # real reply.
    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert "running" in response.text.lower()

    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [m["role"] for m in messages] == ["user"]  # no broken assistant turn saved


def test_chat_reports_clear_message_for_unconfigured_provider(client, app_env, monkeypatch):
    # Real registry wiring, no build_llm monkeypatch: provider "openai" with
    # no OPENAI_API_KEY set should surface as a clear in-stream message, not
    # an unhandled exception - streaming has already committed the 200 by
    # the time this is raised, same as the Ollama-unreachable case above.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_game(app_env / "games", "alpha", provider="openai", model="gpt-4o-mini")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert "OPENAI_API_KEY" in response.text

    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [m["role"] for m in messages] == ["user"]  # no broken assistant turn saved


def test_chat_folds_summary_in_background_without_blocking_reply(client, app_env, monkeypatch):
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    monkeypatch.setattr(summarizer_module, "build_llm", _fake_llm)
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    from roleplay_agent.api.dependencies import get_message_repo, get_session_repo

    message_repo = get_message_repo()
    for i in range(23):  # already well past the fold threshold (KEEP_LAST=20)
        message_repo.add(session_id, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "one more"})

    # The reply itself only ever comes from the generate node's stream.
    assert response.text == "Hello there"

    # TestClient runs background tasks synchronously, so by the time the
    # response comes back the fold has already completed.
    session = get_session_repo().get(session_id)
    assert session.summary == "Hello there"
    assert session.summarized_count > 0


def test_chat_folds_and_embeds_when_memory_recall_enabled(client, app_env, monkeypatch):
    from roleplay_agent.api import dependencies as deps

    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    monkeypatch.setattr(summarizer_module, "build_llm", _fake_llm)
    # Patch what get_embeddings() calls internally, not get_embeddings
    # itself: get_embeddings is @lru_cache'd and conftest's _clear_caches
    # calls .cache_clear() on it every teardown, and other modules import
    # the name directly (`from ..dependencies import get_embeddings`), so
    # replacing that binding wouldn't even be seen by chat.py's own copy.
    monkeypatch.setattr(deps, "build_embeddings", lambda model: _FakeEmbeddings())
    write_game(app_env / "games", "alpha", memory_recall=True)
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    message_repo = deps.get_message_repo()
    for i in range(23):  # already well past the fold threshold (KEEP_LAST=20)
        message_repo.add(session_id, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    client.post(f"/api/sessions/{session_id}/chat", json={"message": "one more"})

    # TestClient runs background tasks synchronously, so the fold - and the
    # embedding it now also stores - has already completed by this point.
    [chunk] = deps.get_embedding_repo().search("alpha", [1.0, 0.0])
    assert chunk.session_id == session_id
    assert "msg 0" in chunk.text


def test_chat_with_memory_recall_includes_recalled_memory_in_prompt(client, app_env, monkeypatch):
    from roleplay_agent.api import dependencies as deps

    seen_prompts = []

    class _CapturingLLM:
        async def ainvoke(self, messages):
            seen_prompts.append(messages[0].content)
            return AIMessage(content="ok")

    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: _CapturingLLM())
    # Patch what get_embeddings() calls internally, not get_embeddings
    # itself: get_embeddings is @lru_cache'd and conftest's _clear_caches
    # calls .cache_clear() on it every teardown, and other modules import
    # the name directly (`from ..dependencies import get_embeddings`), so
    # replacing that binding wouldn't even be seen by chat.py's own copy.
    monkeypatch.setattr(deps, "build_embeddings", lambda model: _FakeEmbeddings())
    write_game(app_env / "games", "alpha", memory_recall=True)
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    # Seed a long-term memory directly, as if an earlier fold had already happened.
    deps.get_embedding_repo().add("alpha", session_id, "The user's dog is named Biscuit.", [1.0, 0.0])

    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "tell me about my dog"})

    assert response.status_code == 200
    assert len(seen_prompts) == 1
    assert "The user's dog is named Biscuit." in seen_prompts[0]


def test_chat_without_memory_recall_never_embeds_the_message(client, app_env, monkeypatch):
    # memory_recall defaults to False - confirms the opt-in stays a true
    # no-op (no embedding call at all) for every game that doesn't set it.
    from roleplay_agent.api import dependencies as deps

    embeddings = _FakeEmbeddings()
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    monkeypatch.setattr(deps, "build_embeddings", lambda model: embeddings)
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    assert embeddings.calls == []


def test_chat_with_skills_enabled_still_replies_normally(client, app_env, monkeypatch):
    # Exercises the real skill_tools wiring (get_skill_tools -> the actual
    # registered "web_research" tool) through the full dependency chain -
    # a game merely declaring a skill mustn't change behavior on a turn
    # where the model doesn't call it.
    monkeypatch.setattr(
        agent_module,
        "build_llm",
        lambda *a, **k: _BindableFakeChatModel(messages=iter([AIMessage(content="Hello there")])),
    )
    write_game(app_env / "games", "alpha", skills=["web_research"])
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    assert response.status_code == 200
    assert response.text == "Hello there"
    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "hi"),
        ("assistant", "Hello there"),
    ]


def test_speak_returns_audio_for_a_voiced_persona(client, app_env, monkeypatch):
    captured = {}

    async def fake_synthesize(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        captured["text"] = text
        captured["voice"] = voice
        return b"RIFF...fake-wav-bytes"

    monkeypatch.setattr(tts_module, "synthesize", fake_synthesize)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak", json={"text": "Hello there"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFF...fake-wav-bytes"
    assert captured == {"text": "Hello there", "voice": "ryan"}


def test_speak_forwards_instruct_for_voice_mode_delivery(client, app_env, monkeypatch):
    # SpeakRequest.instruct is the intended hook for a voice-mode
    # SpeechSegment's `delivery` (see agent/voice.py) - live-verified
    # against mlx-audio's own generate_audio(instruct=...) to actually
    # affect synthesis, not just be accepted and ignored.
    captured = {}

    async def fake_synthesize(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        captured["instruct"] = instruct
        return b"wav"

    monkeypatch.setattr(tts_module, "synthesize", fake_synthesize)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/speak",
        json={"text": "Oh, you have got to be kidding me.", "instruct": "dripping with sarcasm"},
    )

    assert response.status_code == 200
    assert captured["instruct"] == "dripping with sarcasm"


def test_speak_instruct_defaults_to_none(client, app_env, monkeypatch):
    captured = {}

    async def fake_synthesize(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        captured["instruct"] = instruct
        return b"wav"

    monkeypatch.setattr(tts_module, "synthesize", fake_synthesize)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    client.post(f"/api/sessions/{session_id}/speak", json={"text": "Hello there"})

    assert captured["instruct"] is None


def test_speak_422_when_persona_has_no_voice(client, app_env):
    write_game(app_env / "games", "alpha")  # voice defaults to None
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak", json={"text": "Hello there"})

    assert response.status_code == 422
    assert "voice" in response.json()["detail"].lower()


def test_speak_422_for_blank_text(client, app_env):
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak", json={"text": "   "})

    assert response.status_code == 422


def test_speak_missing_session_returns_404(client, app_env):
    response = client.post("/api/sessions/does-not-exist/speak", json={"text": "hi"})
    assert response.status_code == 404


def test_speak_503_when_synthesis_fails(client, app_env, monkeypatch):
    async def failing_synthesize(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        raise TtsError("mlx-audio isn't installed")

    monkeypatch.setattr(tts_module, "synthesize", failing_synthesize)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak", json={"text": "hi"})

    assert response.status_code == 503
    assert "mlx-audio" in response.json()["detail"]


def test_speak_truncates_text_to_configured_max_chars(client, app_env, monkeypatch):
    from roleplay_agent.config.settings import AppConfig, get_app_config
    from roleplay_agent.main import app

    captured = {}

    async def fake_synthesize(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        captured["text"] = text
        return b"wav"

    monkeypatch.setattr(tts_module, "synthesize", fake_synthesize)
    # tts_max_chars lives on AppConfig now (docs/ARCHITECTURE.md's "Config
    # hygiene") - not env-overridable by design, and the /speak route reads
    # it via FastAPI's own Depends(get_app_config) (captured at import
    # time, so monkeypatching the module attribute wouldn't reach it) -
    # app.dependency_overrides is the mechanism FastAPI itself provides for
    # exactly this.
    app.dependency_overrides[get_app_config] = lambda: AppConfig(
        embedding_model="nomic-embed-text", tts_model_repo="x", tts_max_chars=5
    )
    try:
        write_game(app_env / "games", "alpha", voice="ryan")
        session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

        response = client.post(f"/api/sessions/{session_id}/speak", json={"text": "Hello there, friend"})

        assert response.status_code == 200
        assert captured["text"] == "Hello"
    finally:
        del app.dependency_overrides[get_app_config]


def test_speak_stream_returns_pcm_chunks_for_a_voiced_persona(client, app_env, monkeypatch):
    captured = {}

    async def fake_synthesize_stream(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        captured.update(text=text, voice=voice)

        async def chunks():
            yield b"abcd"
            yield b"efgh"

        return 24000, chunks()

    monkeypatch.setattr(tts_module, "synthesize_stream", fake_synthesize_stream)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak-stream", json={"text": "Hello there"})

    assert response.status_code == 200
    # No WAV header to carry it - the sample rate rides out as a header
    # instead, ahead of the raw PCM16LE bytes making up the body.
    assert response.headers["x-sample-rate"] == "24000"
    assert response.content == b"abcdefgh"
    assert captured == {"text": "Hello there", "voice": "ryan"}


def test_speak_stream_422_when_persona_has_no_voice(client, app_env):
    write_game(app_env / "games", "alpha")  # voice defaults to None
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak-stream", json={"text": "Hello there"})

    assert response.status_code == 422
    assert "voice" in response.json()["detail"].lower()


def test_speak_stream_422_for_blank_text(client, app_env):
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak-stream", json={"text": "   "})

    assert response.status_code == 422


def test_speak_stream_503_when_synthesis_fails_before_streaming_starts(client, app_env, monkeypatch):
    async def failing_synthesize_stream(
        pool, text, voice, model_repo, instruct=None, clone_model_repo=None, voice_samples_dir=None
    ):
        raise TtsError("mlx-audio isn't installed")

    monkeypatch.setattr(tts_module, "synthesize_stream", failing_synthesize_stream)
    write_game(app_env / "games", "alpha", voice="ryan")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/speak-stream", json={"text": "hi"})

    assert response.status_code == 503
    assert "mlx-audio" in response.json()["detail"]


def _patch_no_audio_ollama(monkeypatch, model_id="llama3.1"):
    from roleplay_agent.services.llm import capabilities as capabilities_module

    class _NoAudioOllamaClient:
        def list(self):
            class _Model:
                model = model_id
                modified_at = None

            class _Listing:
                models = [_Model()]

            return _Listing()

        def show(self, name):
            class _Show:
                capabilities = ["completion"]

            return _Show()

    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _NoAudioOllamaClient())


def test_voice_turn_422_when_whisper_not_installed(client, app_env, monkeypatch):
    from roleplay_agent.api.routes.gameplay import chat as chat_route
    from roleplay_agent.services.stt import SttUnavailableError

    _patch_no_audio_ollama(monkeypatch)

    def fake_transcribe(audio, model_size):
        raise SttUnavailableError("faster-whisper isn't installed - run `pip install '.[transcribe]'`.")

    monkeypatch.setattr(chat_route, "transcribe_wav_bytes", fake_transcribe)
    write_game(app_env / "games", "alpha", model="llama3.1")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/voice-turn",
        files={"audio": ("clip.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )

    assert response.status_code == 422
    assert "pip install" in response.json()["detail"]


def test_voice_turn_422_when_transcript_is_empty(client, app_env, monkeypatch):
    from roleplay_agent.api.routes.gameplay import chat as chat_route

    _patch_no_audio_ollama(monkeypatch)
    monkeypatch.setattr(chat_route, "transcribe_wav_bytes", lambda audio, model_size: "   ")
    write_game(app_env / "games", "alpha", model="llama3.1")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/voice-turn",
        files={"audio": ("clip.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )

    assert response.status_code == 422
    assert "hear" in response.json()["detail"].lower()


def test_voice_turn_transcribes_locally_for_a_non_audio_model(client, app_env, monkeypatch):
    from roleplay_agent.agents.game_play import voice as voice_module
    from roleplay_agent.agents.game_play.voice import SpeechSegment, VoiceTurn
    from roleplay_agent.api.routes.gameplay import chat as chat_route

    _patch_no_audio_ollama(monkeypatch)

    captured = {}

    def fake_transcribe(audio, model_size):
        captured["audio"] = audio
        captured["model_size"] = model_size
        return "what's the plan for tonight"

    def fake_generate_voice_turn(
        system_prompt, recent, provider, model, num_ctx, keep_alive, transcript=None, audio=None
    ):
        captured["transcript"] = transcript
        captured["audio_kwarg"] = audio
        captured["provider"] = provider
        captured["model"] = model
        return VoiceTurn(
            user_said=transcript,
            segments=[SpeechSegment(text="I was thinking pizza.", delivery=None)],
        )

    monkeypatch.setattr(voice_module, "build_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(chat_route, "transcribe_wav_bytes", fake_transcribe)
    monkeypatch.setattr(chat_route, "generate_voice_turn", fake_generate_voice_turn)
    write_game(app_env / "games", "alpha", model="llama3.1")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/voice-turn",
        files={"audio": ("clip.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_said"] == "what's the plan for tonight"
    assert body["segments"] == [{"text": "I was thinking pizza.", "delivery": None}]
    assert captured["audio"] == b"RIFF....WAVEfmt "
    assert captured["transcript"] == "what's the plan for tonight"
    assert captured["audio_kwarg"] is None
    assert captured["provider"] == "ollama"
    assert captured["model"] == "llama3.1"


def test_voice_turn_missing_session_returns_404(client, app_env):
    response = client.post(
        "/api/sessions/does-not-exist/voice-turn",
        files={"audio": ("clip.wav", b"RIFF", "audio/wav")},
    )
    assert response.status_code == 404


def test_voice_turn_generates_reply_and_persists_transcript(client, app_env, monkeypatch):
    from roleplay_agent.agents.game_play import voice as voice_module
    from roleplay_agent.agents.game_play.voice import SpeechSegment, VoiceTurn
    from roleplay_agent.services.llm import capabilities as capabilities_module

    class _AudioOllamaClient:
        def list(self):
            class _Model:
                model = "gemma-4"
                modified_at = None

            class _Listing:
                models = [_Model()]

            return _Listing()

        def show(self, name):
            class _Show:
                capabilities = ["completion", "audio"]

            return _Show()

    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _AudioOllamaClient())

    captured = {}

    def fake_generate_voice_turn(
        system_prompt, recent, provider, model, num_ctx, keep_alive, audio=None, transcript=None
    ):
        captured["audio"] = audio
        captured["provider"] = provider
        captured["model"] = model
        return VoiceTurn(
            user_said="what's the plan for tonight",
            segments=[
                SpeechSegment(text="I was thinking pizza.", delivery=None),
                SpeechSegment(text="Unless you're feeling something else?", delivery="playful"),
            ],
        )

    monkeypatch.setattr(voice_module, "build_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    from roleplay_agent.api.routes.gameplay import chat as chat_route

    monkeypatch.setattr(chat_route, "generate_voice_turn", fake_generate_voice_turn)
    write_game(app_env / "games", "alpha", model="gemma-4")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/voice-turn",
        files={"audio": ("clip.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_said"] == "what's the plan for tonight"
    assert body["segments"] == [
        {"text": "I was thinking pizza.", "delivery": None},
        {"text": "Unless you're feeling something else?", "delivery": "playful"},
    ]
    assert captured["audio"] == b"RIFF....WAVEfmt "
    assert captured["provider"] == "ollama"
    assert captured["model"] == "gemma-4"

    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "what's the plan for tonight"),
        ("assistant", "I was thinking pizza. Unless you're feeling something else?"),
    ]
