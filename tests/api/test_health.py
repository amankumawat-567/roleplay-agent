from roleplay_agent.api.routes.system import health as health_module


class _FakeModel:
    def __init__(self, model):
        self.model = model


class _FakeListResponse:
    def __init__(self, models):
        self.models = models


def test_health_reports_ok_when_ollama_reachable(client, app_env, monkeypatch):
    class FakeClient:
        def list(self):
            return _FakeListResponse([_FakeModel("llama3.1")])

    monkeypatch.setattr(health_module.ollama, "Client", lambda: FakeClient())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": "reachable", "models": ["llama3.1"]}


def test_health_reports_degraded_when_ollama_unreachable(client, app_env, monkeypatch):
    class FakeClient:
        def list(self):
            raise ConnectionError("boom")

    monkeypatch.setattr(health_module.ollama, "Client", lambda: FakeClient())

    response = client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["ollama"] == "unreachable"
