import pytest

from roleplay_agent.api.routes.studio import game_builder as game_builder_route
from roleplay_agent.components.transcript.media import TranscriptFetchError
from roleplay_agent.config.settings import AppConfig
from roleplay_agent.schema.game_builder import GameDraft
from roleplay_agent.services.llm import capabilities as capabilities_module


def _app_config(**overrides) -> AppConfig:
    return AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
        **overrides,
    )


def _make_nothing_usable(monkeypatch) -> None:
    # resolve_builder_model() always computes the default (no
    # builder_provider/builder_model override exists anymore) - to force
    # its "nothing anywhere is usable" error path, make Ollama unreachable
    # and ensure no hosted provider's API key is set either.
    class _UnreachableOllamaClient:
        def list(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _UnreachableOllamaClient())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class _FakeOllamaModel:
    def __init__(self, name):
        self.model = name
        self.modified_at = None


class _FakeOllamaListResponse:
    def __init__(self, models):
        self.models = models


class _FakeOllamaShowResponse:
    def __init__(self, capabilities):
        self.capabilities = capabilities


class _FakeOllamaClient:
    """Stands in for a real Ollama daemon (see test_health.py's own
    version of this) - every builder route now resolves a model via
    llm/capabilities.py before it does anything else, so these tests need
    a deterministic fake even when they
    aren't testing resolution itself, to stay isolated from whatever's
    actually pulled on the machine running them."""

    def list(self):
        return _FakeOllamaListResponse([_FakeOllamaModel("test-model")])

    def show(self, name):
        return _FakeOllamaShowResponse(["completion"])


@pytest.fixture(autouse=True)
def _fake_ollama(monkeypatch):
    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _FakeOllamaClient())


async def _fake_stream(messages, settings):
    for piece in ["Hello", " there"]:
        yield piece


def _create_session(client, title: str = "New persona", game_id: str | None = None) -> str:
    response = client.post("/api/games/builder/sessions", json={"title": title, "game_id": game_id})
    assert response.status_code == 200
    return response.json()["builder_session_id"]


def test_create_builder_session(client, app_env):
    session_id = _create_session(client, title="New persona")

    response = client.get(f"/api/games/builder/sessions/{session_id}/messages")

    assert response.status_code == 200
    assert response.json()["session"]["title"] == "New persona"
    assert response.json()["session"]["game_id"] is None
    assert response.json()["messages"] == []


def test_builder_session_messages_missing_session_404(client, app_env):
    response = client.get("/api/games/builder/sessions/does-not-exist/messages")
    assert response.status_code == 404


def test_builder_chat_streams_reply_and_persists_both_turns(client, app_env, monkeypatch):
    monkeypatch.setattr(game_builder_route, "stream_builder_reply", _fake_stream)
    session_id = _create_session(client)

    response = client.post(
        f"/api/games/builder/sessions/{session_id}/chat",
        json={"message": "I want a grumpy wizard"},
    )

    assert response.status_code == 200
    assert response.text == "Hello there"

    messages = client.get(f"/api/games/builder/sessions/{session_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "I want a grumpy wizard"),
        ("assistant", "Hello there"),
    ]


def test_builder_chat_prepends_context_without_persisting_it(client, app_env, monkeypatch):
    seen = {}

    async def capture_stream(messages, settings):
        seen["messages"] = messages
        yield "ok"

    monkeypatch.setattr(game_builder_route, "stream_builder_reply", capture_stream)
    session_id = _create_session(client, title="Refining Alex", game_id="alpha")

    client.post(
        f"/api/games/builder/sessions/{session_id}/chat",
        json={"message": "make them grumpier", "context": "Here is the persona as it stands today..."},
    )

    assert seen["messages"][0].content == "Here is the persona as it stands today..."
    assert seen["messages"][1].content == "make them grumpier"
    # The context block is transient grounding, not a real turn - it must
    # never show up in the persisted/resumable transcript.
    messages = client.get(f"/api/games/builder/sessions/{session_id}/messages").json()["messages"]
    assert [m["content"] for m in messages] == ["make them grumpier", "ok"]


def test_builder_chat_reports_clear_error_when_nothing_usable(client, app_env, monkeypatch):
    # Resolving the builder's model now happens before the response starts
    # streaming, so nothing being usable is a real 422 - not a 200 with the
    # error buried in the streamed text the way a mid-stream provider
    # failure still has to be (the HTTP status is already committed by then).
    _make_nothing_usable(monkeypatch)
    session_id = _create_session(client)

    response = client.post(f"/api/games/builder/sessions/{session_id}/chat", json={"message": "hi"})

    assert response.status_code == 422
    assert "No usable model" in response.json()["detail"]
    # Resolved (and failed) before the user's message was ever persisted -
    # no orphaned turn nobody will get a reply to.
    assert client.get(f"/api/games/builder/sessions/{session_id}/messages").json()["messages"] == []


def test_builder_chat_missing_session_404(client, app_env):
    response = client.post("/api/games/builder/sessions/does-not-exist/chat", json={"message": "hi"})
    assert response.status_code == 404


def test_builder_draft_returns_structured_draft(client, app_env, monkeypatch):
    draft = GameDraft(
        title="The Grumpy Wizard",
        tags=["fantasy"],
        persona="A grumpy old wizard.",
        user_role="A young apprentice.",
        script="The apprentice arrives at the tower.",
    )
    monkeypatch.setattr(game_builder_route, "generate_draft", lambda messages, settings: draft)
    session_id = _create_session(client)
    client.post(f"/api/games/builder/sessions/{session_id}/chat", json={"message": "I want a grumpy wizard"})

    response = client.post(f"/api/games/builder/sessions/{session_id}/draft", json={})

    assert response.status_code == 200
    assert response.json() == draft.model_dump()


def test_builder_draft_nothing_usable_returns_422(client, app_env, monkeypatch):
    # Real registry wiring here (no generate_draft monkeypatch) - the
    # global ProviderConfigError exception handler applies since /draft
    # isn't a streaming route.
    _make_nothing_usable(monkeypatch)
    session_id = _create_session(client)

    response = client.post(f"/api/games/builder/sessions/{session_id}/draft", json={})

    assert response.status_code == 422
    assert "No usable model" in response.json()["detail"]


def _draft() -> GameDraft:
    return GameDraft(
        title="The Grumpy Wizard",
        tags=["fantasy"],
        persona="A grumpy old wizard.",
        user_role="A young apprentice.",
        script="The apprentice arrives at the tower.",
    )


def test_builder_draft_from_transcript_returns_structured_draft(client, app_env, monkeypatch):
    calls = []
    monkeypatch.setattr(
        game_builder_route,
        "generate_draft_from_transcript",
        lambda transcript, settings: calls.append(transcript) or _draft(),
    )

    response = client.post(
        "/api/games/builder/draft-from-transcript",
        json={"transcript": "  welcome to my video about a grumpy wizard  "},
    )

    assert response.status_code == 200
    assert response.json() == _draft().model_dump()
    assert calls == ["welcome to my video about a grumpy wizard"]  # stripped


def test_builder_draft_from_transcript_rejects_empty_transcript(client, app_env):
    response = client.post("/api/games/builder/draft-from-transcript", json={"transcript": "   "})

    assert response.status_code == 422


def test_builder_draft_from_transcript_truncates_to_configured_max_chars(client, app_env, monkeypatch):
    monkeypatch.setattr(game_builder_route, "get_app_config", lambda: _app_config(transcript_max_chars=10))
    calls = []
    monkeypatch.setattr(
        game_builder_route,
        "generate_draft_from_transcript",
        lambda transcript, settings: calls.append(transcript) or _draft(),
    )

    client.post("/api/games/builder/draft-from-transcript", json={"transcript": "x" * 1000})

    assert calls == ["x" * 10]


def test_builder_draft_from_video_fetches_transcript_then_drafts(client, app_env, monkeypatch):
    calls = []
    monkeypatch.setattr(
        game_builder_route,
        "fetch_transcript",
        lambda url, max_chars, model_repo, quantize=None: calls.append((url, max_chars)) or "a fetched transcript",
    )
    monkeypatch.setattr(
        game_builder_route,
        "generate_draft_from_transcript",
        lambda transcript, settings: calls.append(transcript) or _draft(),
    )

    response = client.post(
        "/api/games/builder/draft-from-video", json={"url": "https://youtu.be/jNQXAC9IVRw"}
    )

    assert response.status_code == 200
    assert response.json() == _draft().model_dump()
    assert calls[0][0] == "https://youtu.be/jNQXAC9IVRw"
    assert calls[1] == "a fetched transcript"


def test_builder_draft_from_video_returns_422_on_fetch_failure(client, app_env, monkeypatch):
    def raise_error(url, max_chars, model_repo, quantize=None):
        raise TranscriptFetchError("No transcript found for this video")

    monkeypatch.setattr(game_builder_route, "fetch_transcript", raise_error)

    response = client.post("/api/games/builder/draft-from-video", json={"url": "https://youtu.be/nope"})

    assert response.status_code == 422
    assert "No transcript found" in response.json()["detail"]
