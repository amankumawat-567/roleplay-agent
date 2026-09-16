from tests.helpers import write_game


def test_create_session_and_list(client, app_env):
    write_game(app_env / "games", "alpha", starter="user")

    create = client.post("/api/sessions", json={"game_id": "alpha"})
    assert create.status_code == 200
    session_id = create.json()["session_id"]
    assert create.json()["starter"] == "user"

    listing = client.get("/api/sessions")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == session_id
    assert listing.json()[0]["game_id"] == "alpha"


def test_create_session_missing_game_returns_404(client, app_env):
    response = client.post("/api/sessions", json={"game_id": "nope"})
    assert response.status_code == 404


def test_session_messages_round_trip(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.get(f"/api/sessions/{session_id}/messages")

    assert response.status_code == 200
    assert response.json()["session"]["id"] == session_id
    assert response.json()["messages"] == []


def test_session_messages_missing_session_404(client, app_env):
    response = client.get("/api/sessions/does-not-exist/messages")
    assert response.status_code == 404


def test_scheduled_returns_null_when_nothing_pending(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.get(f"/api/sessions/{session_id}/scheduled")

    assert response.status_code == 200
    assert response.json() == {"fire_at": None}


def test_scheduled_returns_the_soonest_pending_followup(client, app_env):
    from roleplay_agent.api import dependencies as deps

    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    followup_repo = deps.get_followup_repo()
    followup_repo.schedule(session_id, fire_at=999999999.0, reason="later")
    followup_repo.schedule(session_id, fire_at=111111111.0, reason="sooner")

    response = client.get(f"/api/sessions/{session_id}/scheduled")

    assert response.json() == {"fire_at": 111111111.0}


def test_scheduled_missing_session_404(client, app_env):
    response = client.get("/api/sessions/does-not-exist/scheduled")
    assert response.status_code == 404


def test_delete_session_removes_it_and_its_messages(client, app_env):
    from roleplay_agent.api import dependencies as deps

    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    # A real message exercises the messages_fts delete trigger, not just an
    # empty session row.
    deps.get_message_repo().add(session_id, "user", "hello there")

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert client.get(f"/api/sessions/{session_id}/messages").status_code == 404
    assert session_id not in [s["id"] for s in client.get("/api/sessions").json()]
    # The FTS index must have dropped the row too, not just the base table -
    # a stale index entry would surface as a phantom search hit.
    assert deps.get_message_repo().search("hello") == []


def test_delete_missing_session_404(client, app_env):
    response = client.delete("/api/sessions/does-not-exist")
    assert response.status_code == 404


def test_rename_session(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.patch(f"/api/sessions/{session_id}", json={"title": "  Rooftop first date  "})

    assert response.status_code == 200
    assert response.json()["title"] == "Rooftop first date"
    assert client.get(f"/api/sessions/{session_id}/messages").json()["session"]["title"] == "Rooftop first date"


def test_rename_session_rejects_blank_title(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.patch(f"/api/sessions/{session_id}", json={"title": "   "})

    assert response.status_code == 422


def test_rename_missing_session_404(client, app_env):
    response = client.patch("/api/sessions/does-not-exist", json={"title": "New title"})
    assert response.status_code == 404


def test_archive_session_hides_it_from_the_default_list(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    response = client.post(f"/api/sessions/{session_id}/archive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None
    assert session_id not in [s["id"] for s in client.get("/api/sessions").json()]
    assert session_id in [s["id"] for s in client.get("/api/sessions/archived").json()]


def test_unarchive_session_restores_it_to_the_default_list(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/archive")

    response = client.post(f"/api/sessions/{session_id}/unarchive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is None
    assert session_id in [s["id"] for s in client.get("/api/sessions").json()]
    assert session_id not in [s["id"] for s in client.get("/api/sessions/archived").json()]


def test_archive_missing_session_404(client, app_env):
    assert client.post("/api/sessions/does-not-exist/archive").status_code == 404


def test_unarchive_missing_session_404(client, app_env):
    assert client.post("/api/sessions/does-not-exist/unarchive").status_code == 404


def test_archived_session_can_still_be_deleted(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/archive")

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert session_id not in [s["id"] for s in client.get("/api/sessions/archived").json()]
