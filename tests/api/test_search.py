from tests.helpers import write_game


def test_search_finds_matching_message(client, app_env):
    write_game(app_env / "games", "alpha", title="Alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    from roleplay_agent.api.dependencies import get_message_repo

    get_message_repo().add(session_id, "user", "Tell me about the lighthouse keeper's daily routine.")

    response = client.get("/api/search", params={"q": "lighthouse"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["session_id"] == session_id
    assert body[0]["title"] == "Alpha"
    assert "lighthouse" in body[0]["snippet"].lower()


def test_search_empty_query_returns_empty(client, app_env):
    response = client.get("/api/search", params={"q": ""})
    assert response.status_code == 200
    assert response.json() == []


def test_search_no_query_param_returns_empty(client, app_env):
    response = client.get("/api/search")
    assert response.status_code == 200
    assert response.json() == []


def test_search_no_matches_returns_empty(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    from roleplay_agent.api.dependencies import get_message_repo

    get_message_repo().add(session_id, "user", "hello there")

    response = client.get("/api/search", params={"q": "nonexistentword"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_dedupes_to_one_result_per_session(client, app_env):
    write_game(app_env / "games", "alpha")
    session_id = client.post("/api/sessions", json={"game_id": "alpha"}).json()["session_id"]

    from roleplay_agent.api.dependencies import get_message_repo

    repo = get_message_repo()
    repo.add(session_id, "user", "talking about dragons")
    repo.add(session_id, "assistant", "yes, dragons are great")

    response = client.get("/api/search", params={"q": "dragons"})
    assert response.status_code == 200
    assert len(response.json()) == 1
