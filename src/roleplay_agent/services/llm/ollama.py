from langchain_ollama import ChatOllama


def build_llm(
    model: str, num_ctx: int, keep_alive: str, base_url: str | None = None, reasoning: bool | None = None
) -> ChatOllama:
    kwargs = {"model": model, "num_ctx": num_ctx, "keep_alive": keep_alive}
    if base_url:
        kwargs["base_url"] = base_url
    # None means "don't pass it at all" - a model/provider's own default
    # stands (configs/models.yaml's `enable_thinking` unset). ChatOllama's
    # own `reasoning` field maps straight onto Ollama's "think" option.
    if reasoning is not None:
        kwargs["reasoning"] = reasoning
    return ChatOllama(**kwargs)
