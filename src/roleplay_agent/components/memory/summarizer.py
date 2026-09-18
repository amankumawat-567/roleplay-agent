from roleplay_agent.services.llm.registry import build_llm
from roleplay_agent.services.storage.models import Message

SUMMARIZE_PROMPT = (
    "Summarize the key facts, emotional state, and progress of this "
    "roleplay so far in 4-6 short bullet points, for internal memory "
    "only. Merge with the previous summary if one is given.\n\n"
    "Previous summary:\n{prev_summary}\n\n"
    "New conversation chunk:\n{convo}\n\nUpdated summary:"
)


def build_summarizer(provider: str, model: str, num_ctx: int, keep_alive: str, enable_thinking: bool | None = None):
    def summarize(prev_summary: str, chunk: list[Message]) -> str:
        convo = "\n".join(f"{m.role}: {m.content}" for m in chunk)
        prompt = SUMMARIZE_PROMPT.format(prev_summary=prev_summary or "(none)", convo=convo)
        llm = build_llm(provider, model, num_ctx, keep_alive, reasoning=enable_thinking)
        return llm.invoke(prompt).content.strip()

    return summarize
