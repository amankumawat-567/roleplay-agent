import time

from tests.helpers import write_game


def test_list_games_returns_valid_games(client, app_env):
    write_game(app_env / "games", "alpha", title="Alpha", tags=["casual"])

    response = client.get("/api/games")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "alpha",
            "title": "Alpha",
            "character_name": None,
            "tags": ["casual"],
            "cover_image": None,
            "provider": "ollama",
            "model": "llama3.1",
        }
    ]


def test_list_games_empty_when_no_games(client, app_env):
    response = client.get("/api/games")
    assert response.status_code == 200
    assert response.json() == []


def _game_payload(**overrides):
    payload = {
        "title": "Alpha",
        "tags": ["casual"],
        "model": "llama3.1",
        "starter": "ai",
        "persona": "A persona.",
        "user_role": "A role.",
        "script": "A script.",
        "research_query": "",
        "num_ctx": None,
    }
    payload.update(overrides)
    return payload


def test_get_game_returns_full_detail(client, app_env):
    write_game(app_env / "games", "alpha", title="Alpha", tags=["casual"])

    response = client.get("/api/games/alpha")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "alpha"
    assert body["persona"] == "A persona."


def test_get_game_404_when_missing(client, app_env):
    response = client.get("/api/games/nope")
    assert response.status_code == 404


def test_create_game_derives_id_from_title(client, app_env):
    response = client.post("/api/games", json=_game_payload(title="My Cool Game"))

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "my-cool-game"
    assert body["title"] == "My Cool Game"

    # actually persisted, not just echoed back
    assert client.get("/api/games/my-cool-game").status_code == 200


def test_create_game_defaults_provider_to_ollama(client, app_env):
    response = client.post("/api/games", json=_game_payload())
    assert response.json()["provider"] == "ollama"


def test_create_game_defaults_voice_to_none(client, app_env):
    response = client.post("/api/games", json=_game_payload())
    assert response.json()["voice"] is None


def test_character_name_defaults_to_none_and_round_trips(client, app_env):
    write_game(app_env / "games", "alpha", title="Rooftop First Date")

    unset = client.get("/api/games/alpha").json()
    assert unset["character_name"] is None
    assert client.get("/api/games").json()[0]["character_name"] is None

    create = client.post("/api/games", json=_game_payload(title="Space Standoff", character_name="Vex"))
    assert create.json()["character_name"] == "Vex"
    game_id = create.json()["id"]
    assert client.get(f"/api/games/{game_id}").json()["character_name"] == "Vex"
    assert next(g for g in client.get("/api/games").json() if g["id"] == game_id)["character_name"] == "Vex"

    update = client.put(f"/api/games/{game_id}", json=_game_payload(title="Space Standoff", character_name="Rex"))
    assert update.json()["character_name"] == "Rex"


def test_create_and_update_game_persists_voice(client, app_env):
    response = client.post("/api/games", json=_game_payload(id="alpha", voice="ryan"))
    assert response.json()["voice"] == "ryan"
    assert client.get("/api/games/alpha").json()["voice"] == "ryan"

    response = client.put("/api/games/alpha", json=_game_payload(voice="serena"))
    assert response.json()["voice"] == "serena"
    assert client.get("/api/games/alpha").json()["voice"] == "serena"


def test_create_game_with_explicit_provider(client, app_env):
    response = client.post("/api/games", json=_game_payload(id="custom-id", provider="openai", model="gpt-4o-mini"))
    assert response.status_code == 201
    assert response.json()["provider"] == "openai"


def test_create_game_with_explicit_id(client, app_env):
    response = client.post("/api/games", json=_game_payload(id="custom-id"))

    assert response.status_code == 201
    assert response.json()["id"] == "custom-id"


def test_create_game_rejects_invalid_explicit_id(client, app_env):
    response = client.post("/api/games", json=_game_payload(id="../escape"))
    assert response.status_code == 422


def test_create_game_conflicts_on_existing_id(client, app_env):
    write_game(app_env / "games", "alpha")

    response = client.post("/api/games", json=_game_payload(id="alpha"))
    assert response.status_code == 409


def test_create_game_invalid_body_returns_422(client, app_env):
    payload = _game_payload()
    del payload["persona"]

    response = client.post("/api/games", json=payload)
    assert response.status_code == 422


def test_update_game_persists_changes(client, app_env):
    write_game(app_env / "games", "alpha", title="Alpha")

    response = client.put("/api/games/alpha", json=_game_payload(title="Alpha Renamed"))

    assert response.status_code == 200
    assert response.json()["title"] == "Alpha Renamed"
    assert client.get("/api/games/alpha").json()["title"] == "Alpha Renamed"


def test_update_game_404_when_missing(client, app_env):
    response = client.put("/api/games/nope", json=_game_payload())
    assert response.status_code == 404


def test_update_game_preserves_research_notes(client, app_env):
    from roleplay_agent.api import dependencies as deps

    write_game(app_env / "games", "alpha")
    deps.get_game_research_repo().set("alpha", "Uses casual phrasing.")

    response = client.put("/api/games/alpha", json=_game_payload(title="Alpha v2"))

    assert response.status_code == 200
    assert response.json()["research_notes"] == "Uses casual phrasing."


def test_delete_game_removes_directory_and_cascades_related_data(client, app_env):
    from roleplay_agent.api import dependencies as deps

    write_game(app_env / "games", "alpha", title="Alpha")

    session_repo = deps.get_session_repo()
    message_repo = deps.get_message_repo()
    embedding_repo = deps.get_embedding_repo()
    followup_repo = deps.get_followup_repo()

    session_id = session_repo.create("alpha", "A Chat")
    message_repo.add(session_id, "user", "hello there")
    embedding_repo.add("alpha", session_id, "hello there", [0.1, 0.2, 0.3])
    followup_repo.schedule(session_id, time.time() + 60, "check in")

    response = client.delete("/api/games/alpha")

    assert response.status_code == 204
    assert not (app_env / "games" / "alpha").exists()
    assert client.get("/api/games/alpha").status_code == 404
    assert session_repo.get(session_id) is None
    assert message_repo.list_for_session(session_id) == []
    assert embedding_repo.search("alpha", [0.1, 0.2, 0.3]) == []
    assert followup_repo.next_for_session(session_id) is None


def test_delete_game_404_when_missing(client, app_env):
    response = client.delete("/api/games/nope")
    assert response.status_code == 404
