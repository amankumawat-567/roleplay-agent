import os
from functools import lru_cache

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel

from roleplay_agent.config.settings import CONFIGS_DIR, PROJECT_ROOT


class ProviderConfigError(ValueError):
    pass


class ProviderConfig(BaseModel):
    kind: str
    base_url: str | None = None
    api_key_env: str | None = None


class ProvidersConfig(BaseModel):
    providers: dict[str, ProviderConfig] = {}


# Ollama needs no configs/providers.yaml entry to work - this is what makes
# it the zero-config default every existing game.yaml already relies on.
_BUILTIN_DEFAULTS = {"ollama": ProviderConfig(kind="ollama")}


def _load_providers_yaml() -> dict:
    path = CONFIGS_DIR / "providers.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_providers_config() -> ProvidersConfig:
    return ProvidersConfig(**_load_providers_yaml())


def get_provider(name: str) -> ProviderConfig:
    config = get_providers_config()
    if name in config.providers:
        return config.providers[name]
    if name in _BUILTIN_DEFAULTS:
        return _BUILTIN_DEFAULTS[name]
    raise ProviderConfigError(f"Unknown provider '{name}' - add it to configs/providers.yaml.")


@lru_cache
def _dotenv_values() -> dict[str, str | None]:
    env_path = PROJECT_ROOT / ".env"
    return dotenv_values(env_path) if env_path.exists() else {}


def resolve_env(name: str) -> str | None:
    """Same precedence config/settings.py uses: a real env var wins over
    .env, since pydantic-settings' own env_file loading never touches
    os.environ for keys outside its declared Settings fields."""
    return os.environ.get(name) or _dotenv_values().get(name)


def resolve_api_key(config: ProviderConfig) -> str:
    if not config.api_key_env:
        raise ProviderConfigError(f"Provider '{config.kind}' is missing 'api_key_env' in configs/providers.yaml.")
    key = resolve_env(config.api_key_env)
    if not key:
        raise ProviderConfigError(f"Set {config.api_key_env} (env var or .env) to use the '{config.kind}' provider.")
    return key
