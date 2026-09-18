from roleplay_agent.services.llm.registry import build_llm


def summarize_style(
    persona: str,
    snippets: list[dict],
    provider: str,
    model: str,
    num_ctx: int,
    keep_alive: str,
    enable_thinking: bool | None = None,
) -> str:
    if not snippets:
        return ""
    joined = "\n\n---\n\n".join(s["text"] for s in snippets)[:8000]
    prompt = (
        "Read this raw text scraped from a few web pages. Pull out only short, "
        "reusable tone/style notes useful for someone roleplaying this persona:\n"
        f"{persona.strip()}\n\n"
        "List common phrases, vocabulary, and speech patterns as a short bullet "
        "list (5-8 bullets max). Do not summarize the pages' content, only the "
        "way people talk in them.\n\nRAW TEXT:\n" + joined
    )
    return build_llm(provider, model, num_ctx, keep_alive, reasoning=enable_thinking).invoke(prompt).content.strip()
