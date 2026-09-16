from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from roleplay_agent.agents.game_play import agent as agent_module
from tests.helpers import write_game


def _fake_llm(*args, **kwargs):
    return GenericFakeChatModel(messages=iter([AIMessage(content="Hey! Good to see you.")]))


def test_full_session_lifecycle(client, app_env, monkeypatch):
    """Create a game -> start a session -> chat -> resume via the messages
    endpoint -> see it in the session list. Exercises the real app wiring
    end-to-end, not just individual units."""
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    write_game(app_env / "games", "friend", starter="user")

    create = client.post("/api/sessions", json={"game_id": "friend"})
    assert create.status_code == 200
    session_id = create.json()["session_id"]

    chat_response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "hey there"})
    assert chat_response.status_code == 200
    assert chat_response.text == "Hey! Good to see you."

    sessions = client.get("/api/sessions").json()
    assert any(s["id"] == session_id for s in sessions)

    messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "hey there"),
        ("assistant", "Hey! Good to see you."),
    ]


def test_first_user_message_becomes_the_session_title(client, app_env, monkeypatch):
    """A0: the placeholder persona-name title gets replaced by a snippet of
    the session's first *user* message, and only that first one - a later
    turn (or a manual rename) is left alone."""
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    write_game(app_env / "games", "friend", starter="user")
    session_id = client.post("/api/sessions", json={"game_id": "friend"}).json()["session_id"]

    client.post(f"/api/sessions/{session_id}/chat", json={"message": "  what should we do tonight?  "})

    session = client.get(f"/api/sessions/{session_id}/messages").json()["session"]
    assert session["title"] == "what should we do tonight?"

    client.post(f"/api/sessions/{session_id}/chat", json={"message": "second turn"})
    session = client.get(f"/api/sessions/{session_id}/messages").json()["session"]
    assert session["title"] == "what should we do tonight?"


def test_long_first_message_title_is_truncated(client, app_env, monkeypatch):
    monkeypatch.setattr(agent_module, "build_llm", _fake_llm)
    write_game(app_env / "games", "friend", starter="user")
    session_id = client.post("/api/sessions", json={"game_id": "friend"}).json()["session_id"]

    long_message = "a" * 80
    client.post(f"/api/sessions/{session_id}/chat", json={"message": long_message})

    session = client.get(f"/api/sessions/{session_id}/messages").json()["session"]
    assert session["title"] == "a" * 50 + "…"
