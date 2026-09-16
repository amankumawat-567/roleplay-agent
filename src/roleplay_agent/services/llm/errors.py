import httpx
from ollama import ResponseError


def describe_llm_error(exc: Exception) -> str:
    """A clear, user-facing message for the two realistic ways talking to
    Ollama fails - it isn't running/reachable at all, or it responded but
    rejected the request (e.g. an unpulled model). Anything else keeps its
    own traceback/500 - this is deliberately narrow, not a catch-all."""
    if isinstance(exc, httpx.TransportError):
        return "Can't reach Ollama - make sure it's running (`ollama serve`)."
    if isinstance(exc, ResponseError):
        return f"Ollama error: {exc.error}"
    return "Unexpected error talking to the model."
