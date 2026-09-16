from typing import Callable

from roleplay_agent.services.storage.repositories import EmbeddingRepository, MessageRepository, SessionRepository


def fold_overflow_into_summary(
    session_repo: SessionRepository,
    message_repo: MessageRepository,
    session_id: str,
    keep_last: int,
    summarize_fn,
    *,
    embedding_repo: EmbeddingRepository | None = None,
    embed_fn: Callable[[str], list[float]] | None = None,
    game_id: str | None = None,
) -> bool:
    """If there are messages older than keep_last that haven't been folded
    into the running summary yet, fold them in now via
    summarize_fn(prev_summary, chunk). Safe to call anytime, e.g. as a
    background task after a turn - a no-op when there's nothing new to
    fold, and self-healing if a previous fold was skipped or is still
    catching up. Returns whether a fold actually happened.

    When embedding_repo/embed_fn/game_id are given (section F's long-term
    memory, opt-in per game via Game.memory_recall), the chunk is also
    embedded and stored *before* it gets compressed into the summary -
    fine detail is captured right before it would otherwise be lost for
    good. Omit them (the default) to fold without indexing anything."""
    session = session_repo.get(session_id)
    msgs = message_repo.list_for_session(session_id)
    keep_from = max(0, len(msgs) - keep_last)

    if keep_from > session.summarized_count:
        chunk = msgs[session.summarized_count : keep_from]
        if embedding_repo is not None and embed_fn is not None and game_id is not None:
            text = "\n".join(f"{m.role}: {m.content}" for m in chunk)
            embedding_repo.add(game_id, session_id, text, embed_fn(text))
        summary = summarize_fn(session.summary, chunk)
        session_repo.update_summary(session_id, summary, keep_from)
        return True
    return False
