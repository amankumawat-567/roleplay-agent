from langchain_openai import ChatOpenAI

from roleplay_agent.services.llm.providers import ProviderConfig, resolve_api_key


def build_llm(model: str, config: ProviderConfig) -> ChatOpenAI:
    return ChatOpenAI(model=model, api_key=resolve_api_key(config))
