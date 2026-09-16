import pytest

from roleplay_agent.services.llm.providers import (
    ProviderConfig,
    ProviderConfigError,
    get_provider,
    resolve_api_key,
    resolve_env,
)


def test_get_provider_ollama_is_the_zero_config_default():
    config = get_provider("ollama")
    assert config.kind == "ollama"


def test_get_provider_openai_resolves_from_providers_yaml():
    config = get_provider("openai")
    assert config.kind == "openai"
    assert config.api_key_env == "OPENAI_API_KEY"


def test_get_provider_anthropic_resolves_from_providers_yaml():
    config = get_provider("anthropic")
    assert config.kind == "anthropic"
    assert config.api_key_env == "ANTHROPIC_API_KEY"


def test_get_provider_unknown_raises_clear_error():
    with pytest.raises(ProviderConfigError, match="does-not-exist"):
        get_provider("does-not-exist")


def test_resolve_env_prefers_os_environ_over_dotenv(monkeypatch):
    monkeypatch.setenv("ROLEPLAY_TEST_KEY", "from-environ")
    assert resolve_env("ROLEPLAY_TEST_KEY") == "from-environ"


def test_resolve_env_missing_returns_none(monkeypatch):
    monkeypatch.delenv("ROLEPLAY_TEST_KEY_MISSING", raising=False)
    assert resolve_env("ROLEPLAY_TEST_KEY_MISSING") is None


def test_resolve_api_key_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    assert resolve_api_key(get_provider("openai")) == "sk-test-123"


def test_resolve_api_key_missing_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        resolve_api_key(get_provider("openai"))


def test_resolve_api_key_without_api_key_env_configured_raises():
    with pytest.raises(ProviderConfigError):
        resolve_api_key(ProviderConfig(kind="custom"))
