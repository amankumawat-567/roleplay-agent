from roleplay_agent.services.llm import capabilities as capabilities_module


class _FakeModel:
    def __init__(self, name):
        self.model = name
        self.modified_at = None


class _FakeListResponse:
    def __init__(self, models):
        self.models = models


class _FakeShowResponse:
    def __init__(self, capabilities):
        self.capabilities = capabilities


class _FakeOllamaClient:
    def list(self):
        return _FakeListResponse([_FakeModel("local-model")])

    def show(self, name):
        return _FakeShowResponse(["completion"])


class _UnreachableOllamaClient:
    def list(self):
        raise ConnectionError("boom")


def test_list_models_returns_ollama_when_reachable(client, app_env, monkeypatch):
    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _FakeOllamaClient())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_provider"] == "ollama"
    assert body["providers"] == [
        {"provider": "ollama", "models": [{"id": "local-model", "capabilities": ["completion"], "modified_at": None}]}
    ]


def test_list_models_omits_ollama_entirely_when_unreachable(client, app_env, monkeypatch):
    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _UnreachableOllamaClient())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    assert body["providers"] == []
    assert body["default_provider"] is None


def test_list_models_includes_hosted_provider_only_with_a_configured_key(client, app_env, monkeypatch):
    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: _UnreachableOllamaClient())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    response = client.get("/api/models")

    assert response.status_code == 200
    body = response.json()
    assert [p["provider"] for p in body["providers"]] == ["anthropic"]
    assert body["default_provider"] == "anthropic"
