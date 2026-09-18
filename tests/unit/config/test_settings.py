import pytest

from roleplay_agent.config import settings as settings_module
from roleplay_agent.config.settings import AppConfig, ConfigError, get_app_config


@pytest.fixture(autouse=True)
def _reset_app_config_cache():
    # get_app_config() is @lru_cache'd at module scope - a test that swaps
    # out settings_module._defaults needs a clean cache both before its own
    # assertions and afterward, so it can't leak a stale/fake AppConfig
    # into whichever test runs next.
    get_app_config.cache_clear()
    yield
    get_app_config.cache_clear()


def test_app_config_is_not_a_basesettings_env_overridable_object():
    # The structural guarantee docs/ARCHITECTURE.md's "Config hygiene"
    # exists for: AppConfig is a plain BaseModel, not BaseSettings, so it
    # has no env_prefix/env_file machinery at all to accidentally read from.
    assert not hasattr(AppConfig, "model_config") or "env_prefix" not in (AppConfig.model_config or {})


def test_get_app_config_raises_clear_error_when_embedding_model_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {"stt_model_repo": "openai/whisper-tiny", "tts_backend": "chatterbox", "tts_chatterbox_model_repo": "x"},
    )

    with pytest.raises(ConfigError, match="embedding_model"):
        get_app_config()


def test_get_app_config_raises_clear_error_when_stt_model_repo_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {"embedding_model": "nomic-embed-text", "tts_backend": "chatterbox", "tts_chatterbox_model_repo": "x"},
    )

    with pytest.raises(ConfigError, match="stt_model_repo"):
        get_app_config()


def test_get_app_config_raises_clear_error_when_tts_backend_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module, "_defaults", {"embedding_model": "nomic-embed-text", "stt_model_repo": "openai/whisper-tiny"}
    )

    with pytest.raises(ConfigError, match="tts_backend"):
        get_app_config()


def test_get_app_config_raises_clear_error_when_chatterbox_model_repo_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {
            "embedding_model": "nomic-embed-text",
            "stt_model_repo": "openai/whisper-tiny",
            "tts_backend": "chatterbox",
        },
    )

    with pytest.raises(ConfigError, match="tts_chatterbox_model_repo"):
        get_app_config()


def test_get_app_config_raises_clear_error_when_qwen3_model_repo_missing(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {"embedding_model": "nomic-embed-text", "stt_model_repo": "openai/whisper-tiny", "tts_backend": "qwen3"},
    )

    with pytest.raises(ConfigError, match="tts_qwen3_model_repo"):
        get_app_config()


def test_get_app_config_lists_every_missing_required_key_at_once(monkeypatch):
    monkeypatch.setattr(settings_module, "_defaults", {"tts_backend": "chatterbox"})

    with pytest.raises(ConfigError) as exc_info:
        get_app_config()

    assert "embedding_model" in str(exc_info.value)
    assert "stt_model_repo" in str(exc_info.value)
    assert "tts_chatterbox_model_repo" in str(exc_info.value)


def test_get_app_config_succeeds_when_required_keys_present(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {
            "embedding_model": "nomic-embed-text",
            "stt_model_repo": "openai/whisper-tiny",
            "tts_backend": "chatterbox",
            "tts_chatterbox_model_repo": "ResembleAI/chatterbox-turbo",
            "keep_alive": "5m",
        },
    )

    app_config = get_app_config()

    assert app_config.embedding_model == "nomic-embed-text"
    assert app_config.stt_model_repo == "openai/whisper-tiny"
    assert app_config.tts_backend == "chatterbox"
    assert app_config.tts_chatterbox_model_repo == "ResembleAI/chatterbox-turbo"
    assert app_config.keep_alive == "5m"  # non-required fields still flow through from configs/*.yaml


def test_get_app_config_succeeds_with_qwen3_tts_backend(monkeypatch):
    monkeypatch.setattr(
        settings_module,
        "_defaults",
        {
            "embedding_model": "nomic-embed-text",
            "stt_model_repo": "facebook/wav2vec2-base-960h",
            "tts_backend": "qwen3",
            "tts_qwen3_model_repo": "mlx-community/x",
        },
    )

    app_config = get_app_config()

    assert app_config.stt_model_repo == "facebook/wav2vec2-base-960h"
    assert app_config.tts_backend == "qwen3"
    assert app_config.tts_qwen3_model_repo == "mlx-community/x"


def _required_defaults(**overrides) -> dict:
    base = {
        "embedding_model": "nomic-embed-text",
        "stt_model_repo": "openai/whisper-tiny",
        "tts_backend": "chatterbox",
        "tts_chatterbox_model_repo": "x",
    }
    base.update(overrides)
    return base


def test_builder_provider_and_model_default_to_none_when_unset(monkeypatch):
    monkeypatch.setattr(settings_module, "_defaults", _required_defaults())

    app_config = get_app_config()

    assert app_config.builder_provider is None
    assert app_config.builder_model is None


def test_enable_thinking_defaults_to_none_when_unset(monkeypatch):
    monkeypatch.setattr(settings_module, "_defaults", _required_defaults())

    app_config = get_app_config()

    assert app_config.enable_thinking is None


def test_enable_thinking_flows_through_when_set(monkeypatch):
    monkeypatch.setattr(settings_module, "_defaults", _required_defaults(enable_thinking=False))

    app_config = get_app_config()

    assert app_config.enable_thinking is False
