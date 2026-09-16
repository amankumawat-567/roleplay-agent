from langchain_ollama import ChatOllama


def build_llm(model: str, num_ctx: int, keep_alive: str, base_url: str | None = None) -> ChatOllama:
    kwargs = {"model": model, "num_ctx": num_ctx, "keep_alive": keep_alive}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOllama(**kwargs)
