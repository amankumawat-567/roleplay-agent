"""Model discovery + capability cache - no hardcoded default model/provider
anywhere. Ollama is queried live
(``ollama.Client().list()``/``.show()``, the same calls `api/routes/health.py`
already uses); a hosted provider (OpenAI/Anthropic) has no live "what can
this model do" API worth relying on, so its capabilities come from a small
hand-maintained table below, updated manually as models are added - what
*is* checked live for a hosted provider is whether it's usable at all right
now (`llm.providers.resolve_api_key` succeeding)."""

import json
import random
import time

import ollama
from pydantic import BaseModel

from roleplay_agent.services.llm.providers import (
    ProviderConfigError,
    get_providers_config,
    resolve_api_key,
)
from roleplay_agent.services.storage.repositories import SettingsRepository

# Refreshed on this TTL (checked on every call, actually refreshed only
# once it's stale) - not recomputed per request, but still cheap enough
# that a server restart or a long-idle app always sees current state.
CACHE_TTL_SECONDS = 300

# Ollama's own capability tag for a model with a real audio encoder in its
# architecture (see docs/ARCHITECTURE.md's "Voice mode": confirmed live to
# mean audio *input*, not output - distinct from the shipped TTS, which is
# chat-model-independent). Section F's voice mode is gated on this, not a
# toggle every persona grows.
AUDIO_INPUT_CAPABILITY = "audio"

# Every hosted model listed here is treated as reachable (and
# 'completion'-capable) purely off whether its provider's api_key_env is
# set - there's no live capability-discovery API worth calling per model
# the way Ollama's `show()` is. Order matters: the first entry per
# provider is what a new persona/the AI builder defaults to when this
# provider is chosen.
HOSTED_MODEL_CAPABILITIES: dict[str, list[str]] = {
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    "anthropic": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "claude-opus-4-20250514"],
}


class ModelInfo(BaseModel):
    id: str
    capabilities: list[str] = []
    # None for a hosted model - no real "last updated" timestamp is worth
    # tracking for those the way an Ollama pull's mtime is.
    modified_at: float | None = None


class ProviderModels(BaseModel):
    provider: str
    models: list[ModelInfo]


def _ollama_models() -> ProviderModels | None:
    """None when Ollama isn't reachable at all - that provider simply
    doesn't appear in the result, not shown disabled/greyed-out."""
    try:
        client = ollama.Client()
        listing = client.list()
    except Exception:
        return None

    models = []
    for entry in listing.models:
        try:
            capabilities = list(client.show(entry.model).capabilities or [])
        except Exception:
            capabilities = []
        modified_at = entry.modified_at.timestamp() if entry.modified_at else None
        models.append(ModelInfo(id=entry.model, capabilities=capabilities, modified_at=modified_at))
    # Newest pull/update first - what default_chat_model() below picks
    # from, and a sensible "top of the list" order for a picker too.
    models.sort(key=lambda m: m.modified_at or 0, reverse=True)
    return ProviderModels(provider="ollama", models=models) if models else None


def _hosted_models() -> list[ProviderModels]:
    result = []
    for provider_name, model_ids in HOSTED_MODEL_CAPABILITIES.items():
        config = get_providers_config().providers.get(provider_name)
        if config is None:
            continue
        try:
            resolve_api_key(config)
        except ProviderConfigError:
            continue  # no key configured - doesn't appear at all, see above
        result.append(
            ProviderModels(
                provider=provider_name,
                models=[ModelInfo(id=model_id, capabilities=["completion"]) for model_id in model_ids],
            )
        )
    return result


def _refresh(settings_repo: SettingsRepository) -> list[ProviderModels]:
    providers = []
    ollama_models = _ollama_models()
    if ollama_models:
        providers.append(ollama_models)
    providers.extend(_hosted_models())

    settings_repo.set(
        "model_capabilities",
        json.dumps({"checked_at": time.time(), "providers": [p.model_dump() for p in providers]}),
    )
    return providers


def get_available_models(settings_repo: SettingsRepository, force_refresh: bool = False) -> list[ProviderModels]:
    """The capability cache itself - the `app_settings` table's
    `model_capabilities` key, reserved for exactly this since the Phase 3
    restructure. `force_refresh` is for tests and any future manual
    "refresh now" affordance."""
    if not force_refresh:
        raw = settings_repo.get("model_capabilities")
        if raw is not None:
            try:
                data = json.loads(raw)
                if time.time() - data["checked_at"] < CACHE_TTL_SECONDS:
                    return [ProviderModels(**p) for p in data["providers"]]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # a corrupt cache value just means "refresh now"
    return _refresh(settings_repo)


def default_chat_model(providers: list[ProviderModels]) -> tuple[str, str] | None:
    """The single "the default" model, computed rather than configured -
    the most recently pulled/updated Ollama model with `completion` in its
    capabilities (Ollama's zero-setup local models come first, by name -
    not merely by whatever order `providers` happens to be given in),
    falling through to a hosted provider's own first chat-capable model
    (no real timestamps to sort hosted models by) only when no Ollama
    model qualifies. None only when nothing anywhere is usable."""
    ordered = sorted(providers, key=lambda p: 0 if p.provider == "ollama" else 1)
    for provider in ordered:
        chat_capable = [m for m in provider.models if "completion" in m.capabilities]
        if chat_capable:
            return provider.provider, chat_capable[0].id
    return None


def has_capability(providers: list[ProviderModels], provider: str, model: str, capability: str) -> bool:
    """Whether `provider`/`model` (a game's own fields) currently reports
    `capability` in the capability cache - False for a model that isn't
    reachable/listed at all, same as it not existing for any other purpose
    here. Used both for F1's voice-mode gate (`AUDIO_INPUT_CAPABILITY`) and
    is the natural place any future per-model gate would live too."""
    match = next((p for p in providers if p.provider == provider), None)
    if match is None:
        return False
    model_info = next((m for m in match.models if m.id == model), None)
    return model_info is not None and capability in model_info.capabilities


def get_default_provider(settings_repo: SettingsRepository, providers: list[ProviderModels]) -> str | None:
    """Random once among whichever providers are actually reachable, then
    stable - configs/providers.yaml's old static `default_provider: ollama`
    silently favored Ollama even with other providers configured and
    working, purely because it was listed first. Persisted to the
    `app_settings` table's `default_provider` key (a bare string, a
    sibling to the capability cache) so it's chosen once, not re-rolled on
    every request."""
    reachable = {p.provider for p in providers}
    if not reachable:
        return None

    stored = settings_repo.get("default_provider")
    if stored in reachable:
        return stored

    chosen = random.choice(sorted(reachable))
    settings_repo.set("default_provider", chosen)
    return chosen


def resolve_builder_model(settings_repo: SettingsRepository) -> tuple[str, str]:
    """The AI game-builder chat (A2) always runs on the same computed
    "most recently pulled/updated" default a brand-new persona gets (see
    default_chat_model) - no config override, so the builder can't be left
    pinned to a stale model after a fresh Ollama pull."""
    resolved = default_chat_model(get_available_models(settings_repo))
    if resolved is None:
        raise ProviderConfigError(
            "No usable model found for the AI builder - pull an Ollama model, or configure a "
            "hosted provider's API key."
        )
    return resolved


# A game.yaml's `model:` sentinel meaning "compute it" - see resolve_game_model.
GAME_MODEL_DEFAULT = "default"


def resolve_game_model(provider: str, model: str, settings_repo: SettingsRepository) -> tuple[str, str]:
    """A persona's `game.yaml` can set `model: default` instead of pinning a
    specific model at authoring time - resolved here to the same computed
    "most recently pulled/updated" pick a brand-new persona gets (see
    default_chat_model), every time this is called (so a session keeps
    following whatever's currently best, not whatever was newest the first
    time this game was loaded).

    `provider` is ignored whenever this fires - `Game.provider` defaults to
    `"ollama"` (games/models.py), so there's no way to tell "the author
    deliberately chose ollama" from "the field was simply never set."
    `model: default` therefore always means "pick the single best
    currently-available option across every reachable provider," never
    "stay on this game's own provider field."."""
    if model != GAME_MODEL_DEFAULT:
        return provider, model

    resolved = default_chat_model(get_available_models(settings_repo))
    if resolved is None:
        raise ProviderConfigError(
            "No usable chat model found for this persona's `model: default` - pull an Ollama model, "
            "configure a hosted provider's API key, or set an explicit model in its game.yaml."
        )
    return resolved
