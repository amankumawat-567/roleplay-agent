from tests.helpers import write_game


def test_get_profile_defaults_when_never_set(client, app_env):
    response = client.get("/api/profile")

    assert response.status_code == 200
    assert response.json() == {"avatar_id": "profile-avatar", "display_name": None}


def test_put_then_get_profile_round_trips(client, app_env):
    put = client.put("/api/profile", json={"avatar_id": "ryan", "display_name": "  Johnny  "})
    assert put.status_code == 200
    assert put.json() == {"avatar_id": "ryan", "display_name": "Johnny"}

    get = client.get("/api/profile")
    assert get.json() == {"avatar_id": "ryan", "display_name": "Johnny"}


def test_put_profile_blank_display_name_stores_none(client, app_env):
    client.put("/api/profile", json={"avatar_id": "ryan", "display_name": "   "})

    response = client.get("/api/profile")

    assert response.json()["display_name"] is None


def test_profile_stats_all_zero_with_no_personas_or_sessions(client, app_env):
    response = client.get("/api/profile/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["stats"] == {
        "persona_count": 0,
        "session_count": 0,
        "message_count": 0,
        "played_seconds": 0,
    }
    assert body["recent_activity"] == []


def test_profile_stats_counts_personas_sessions_and_messages(client, app_env):
    write_game(app_env / "games", "alpha")
    write_game(app_env / "games", "beta")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    response = client.get("/api/profile/stats")

    body = response.json()
    assert body["stats"]["persona_count"] == 2
    assert body["stats"]["session_count"] == 1
    assert body["stats"]["message_count"] == 1  # one user-sent message


def test_profile_stats_recent_activity_includes_sessions_and_personas(client, app_env):
    write_game(app_env / "games", "alpha")
    client.post("/api/sessions", json={"game_id": "alpha"})

    response = client.get("/api/profile/stats")

    kinds = {item["kind"] for item in response.json()["recent_activity"]}
    assert kinds == {"session", "persona"}


def test_profile_stats_totals_still_count_archived_sessions(client, app_env):
    # Same reasoning as Library's own stats (see docs/ARCHITECTURE.md's
    # "Archiving a session"): archiving hides a chat from day-to-day lists,
    # it doesn't erase the time you spent in it from your all-time totals.
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/archive")

    response = client.get("/api/profile/stats")

    assert response.json()["stats"]["session_count"] == 1


def test_profile_stats_recent_activity_excludes_archived_sessions(client, app_env):
    # Recent activity is "what's fresh," the same "not archived" scoping
    # A4's per-persona sidebar already uses - unlike the totals above.
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/archive")

    response = client.get("/api/profile/stats")

    assert all(item["kind"] != "session" for item in response.json()["recent_activity"])
