from langchain_anthropic import ChatAnthropic

from roleplay_agent.services.llm.providers import ProviderConfig, resolve_api_key


def build_llm(model: str, config: ProviderConfig) -> ChatAnthropic:
    return ChatAnthropic(model=model, api_key=resolve_api_key(config))
