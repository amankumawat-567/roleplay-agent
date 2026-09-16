import pytest

from roleplay_agent.config.settings import AppConfig
from roleplay_agent.services.llm import capabilities as capabilities_module
from roleplay_agent.services.llm.capabilities import (
    ModelInfo,
    ProviderModels,
    default_chat_model,
    get_available_models,
    get_default_provider,
    has_capability,
    resolve_builder_model,
)
from roleplay_agent.services.llm.providers import ProviderConfigError
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import SettingsRepository


class _FakeModel:
    def __init__(self, name, modified_at=None):
        self.model = name
        self.modified_at = modified_at


class _FakeListResponse:
    def __init__(self, models):
        self.models = models


class _FakeShowResponse:
    def __init__(self, capabilities):
        self.capabilities = capabilities


class _FakeOllamaClient:
    def __init__(self, models=None, capabilities=None, unreachable=False):
        self._models = models or []
        self._capabilities = capabilities or {}
        self._unreachable = unreachable

    def list(self):
        if self._unreachable:
            raise ConnectionError("boom")
        return _FakeListResponse(self._models)

    def show(self, name):
        return _FakeShowResponse(self._capabilities.get(name, []))


def _settings_repo(tmp_path) -> SettingsRepository:
    db = Database(tmp_path / "test.db")
    db.init_db()
    return SettingsRepository(db)


def _app_config(**overrides) -> AppConfig:
    return AppConfig(embedding_model="nomic-embed-text", tts_model_repo="x", **overrides)


def _mock_ollama(monkeypatch, client: _FakeOllamaClient) -> None:
    monkeypatch.setattr(capabilities_module.ollama, "Client", lambda: client)


def test_get_available_models_returns_empty_when_ollama_unreachable_and_no_keys(tmp_path, monkeypatch):
    _mock_ollama(monkeypatch, _FakeOllamaClient(unreachable=True))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert get_available_models(_settings_repo(tmp_path)) == []


def test_get_available_models_lists_ollama_models_sorted_by_recency(tmp_path, monkeypatch):
    import datetime

    older = datetime.datetime(2026, 1, 1)
    newer = datetime.datetime(2026, 6, 1)
    client = _FakeOllamaClient(
        models=[_FakeModel("old-model", older), _FakeModel("new-model", newer)],
        capabilities={"old-model": ["completion"], "new-model": ["completion", "vision"]},
    )
    _mock_ollama(monkeypatch, client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    providers = get_available_models(_settings_repo(tmp_path))

    assert len(providers) == 1
    assert providers[0].provider == "ollama"
    assert [m.id for m in providers[0].models] == ["new-model", "old-model"]
    assert providers[0].models[0].capabilities == ["completion", "vision"]


def test_get_available_models_excludes_hosted_provider_without_api_key(tmp_path, monkeypatch):
    _mock_ollama(monkeypatch, _FakeOllamaClient(unreachable=True))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    providers = get_available_models(_settings_repo(tmp_path))

    assert [p.provider for p in providers] == ["anthropic"]
    assert all("completion" in m.capabilities for m in providers[0].models)


def test_get_available_models_caches_and_respects_ttl(tmp_path, monkeypatch):
    client = _FakeOllamaClient(models=[_FakeModel("m1")], capabilities={"m1": ["completion"]})
    _mock_ollama(monkeypatch, client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings_repo = _settings_repo(tmp_path)

    get_available_models(settings_repo)
    calls = []
    monkeypatch.setattr(client, "list", lambda: calls.append(1) or _FakeListResponse([_FakeModel("m1")]))

    get_available_models(settings_repo)  # within TTL - reads the cached value, doesn't call list() again

    assert calls == []


def test_get_available_models_force_refresh_bypasses_cache(tmp_path, monkeypatch):
    client = _FakeOllamaClient(models=[_FakeModel("m1")], capabilities={"m1": ["completion"]})
    _mock_ollama(monkeypatch, client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings_repo = _settings_repo(tmp_path)

    get_available_models(settings_repo)
    calls = []
    monkeypatch.setattr(client, "list", lambda: calls.append(1) or _FakeListResponse([_FakeModel("m1")]))

    get_available_models(settings_repo, force_refresh=True)

    assert calls == [1]


def test_default_chat_model_prefers_ollama_over_hosted():
    providers = [
        ProviderModels(provider="openai", models=[ModelInfo(id="gpt-4o-mini", capabilities=["completion"])]),
        ProviderModels(provider="ollama", models=[ModelInfo(id="llama3.1", capabilities=["completion"])]),
    ]
    assert default_chat_model(providers) == ("ollama", "llama3.1")


def test_default_chat_model_falls_through_to_hosted_when_no_ollama():
    providers = [ProviderModels(provider="openai", models=[ModelInfo(id="gpt-4o-mini", capabilities=["completion"])])]
    assert default_chat_model(providers) == ("openai", "gpt-4o-mini")


def test_default_chat_model_ignores_non_chat_capable_models():
    providers = [ProviderModels(provider="ollama", models=[ModelInfo(id="embed-only", capabilities=["embedding"])])]
    assert default_chat_model(providers) is None


def test_default_chat_model_none_when_nothing_available():
    assert default_chat_model([]) is None


def test_get_default_provider_persists_once_chosen(tmp_path, monkeypatch):
    settings_repo = _settings_repo(tmp_path)
    providers = [ProviderModels(provider="ollama", models=[ModelInfo(id="m1", capabilities=["completion"])])]

    first = get_default_provider(settings_repo, providers)
    assert first == "ollama"

    assert settings_repo.get("default_provider") == "ollama"

    # Called again - same stable answer, not re-rolled.
    assert get_default_provider(settings_repo, providers) == "ollama"


def test_get_default_provider_re_rolls_when_stored_choice_no_longer_reachable(tmp_path):
    settings_repo = _settings_repo(tmp_path)
    settings_repo.set("default_provider", "openai")

    providers = [ProviderModels(provider="ollama", models=[ModelInfo(id="m1", capabilities=["completion"])])]

    assert get_default_provider(settings_repo, providers) == "ollama"


def test_get_default_provider_none_when_nothing_reachable(tmp_path):
    assert get_default_provider(_settings_repo(tmp_path), []) is None


def test_resolve_builder_model_uses_explicit_override_with_no_lookup(tmp_path, monkeypatch):
    def _boom():
        raise AssertionError("should not touch the capability cache at all")

    monkeypatch.setattr(capabilities_module, "get_available_models", lambda *a, **k: _boom())
    app_config = _app_config(builder_provider="openai", builder_model="gpt-4o-mini")

    assert resolve_builder_model(_settings_repo(tmp_path), app_config) == ("openai", "gpt-4o-mini")


def test_resolve_builder_model_computes_default_when_unset(tmp_path, monkeypatch):
    _mock_ollama(monkeypatch, _FakeOllamaClient(models=[_FakeModel("m1")], capabilities={"m1": ["completion"]}))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert resolve_builder_model(_settings_repo(tmp_path), _app_config()) == ("ollama", "m1")


def test_resolve_builder_model_raises_when_nothing_usable(tmp_path, monkeypatch):
    _mock_ollama(monkeypatch, _FakeOllamaClient(unreachable=True))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ProviderConfigError):
        resolve_builder_model(_settings_repo(tmp_path), _app_config())


def test_resolve_builder_model_explicit_provider_no_model_uses_its_own_best_model(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _mock_ollama(monkeypatch, _FakeOllamaClient(models=[_FakeModel("m1")], capabilities={"m1": ["completion"]}))

    provider, model = resolve_builder_model(_settings_repo(tmp_path), _app_config(builder_provider="openai"))

    assert provider == "openai"
    assert model  # the table's first openai model, not Ollama's


def test_resolve_builder_model_explicit_provider_missing_key_raises_precise_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        resolve_builder_model(_settings_repo(tmp_path), _app_config(builder_provider="openai"))


def test_has_capability_true_when_model_reports_it():
    providers = [
        ProviderModels(
            provider="ollama",
            models=[ModelInfo(id="gemma-4", capabilities=["completion", "audio"])],
        )
    ]
    assert has_capability(providers, "ollama", "gemma-4", "audio") is True


def test_has_capability_false_when_model_lacks_it():
    providers = [
        ProviderModels(provider="ollama", models=[ModelInfo(id="llama3.1", capabilities=["completion"])])
    ]
    assert has_capability(providers, "ollama", "llama3.1", "audio") is False


def test_has_capability_false_when_provider_not_listed():
    assert has_capability([], "ollama", "llama3.1", "audio") is False


def test_has_capability_false_when_model_not_listed():
    providers = [ProviderModels(provider="ollama", models=[ModelInfo(id="other-model", capabilities=["audio"])])]
    assert has_capability(providers, "ollama", "llama3.1", "audio") is False
