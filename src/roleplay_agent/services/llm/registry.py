from langchain_core.language_models import BaseChatModel

from roleplay_agent.services.llm import anthropic, ollama, openai
from roleplay_agent.services.llm.providers import ProviderConfigError, get_provider


def build_llm(provider: str, model: str, num_ctx: int, keep_alive: str) -> BaseChatModel:
    """Small factory keyed by provider kind. num_ctx/keep_alive are
    Ollama-specific knobs - hosted providers just ignore them, so every
    call site can pass the same four arguments regardless of provider."""
    config = get_provider(provider)
    if config.kind == "ollama":
        return ollama.build_llm(model, num_ctx, keep_alive, base_url=config.base_url)
    if config.kind == "openai":
        return openai.build_llm(model, config)
    if config.kind == "anthropic":
        return anthropic.build_llm(model, config)
    raise ProviderConfigError(f"Unknown provider kind: {config.kind!r}")
