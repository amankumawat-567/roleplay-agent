import httpx

from roleplay_agent.api.routes.studio import research as research_module
from tests.helpers import write_game


def test_research_missing_game_returns_404(client, app_env):
    response = client.post("/api/games/does-not-exist/research")
    assert response.status_code == 404


def test_research_returns_503_when_ollama_unreachable(client, app_env, monkeypatch):
    write_game(app_env / "games", "alpha", research_query="test query")

    class FailingResearcher:
        def research(self, game_id):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(research_module, "get_researcher", lambda: FailingResearcher())

    response = client.post("/api/games/alpha/research")

    assert response.status_code == 503
    assert "running" in response.json()["detail"].lower()
