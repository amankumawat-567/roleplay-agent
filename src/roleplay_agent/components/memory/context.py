from roleplay_agent.services.storage.repositories import MessageRepository, SessionRepository


def get_context(
    session_repo: SessionRepository, message_repo: MessageRepository, session_id: str, keep_last: int
):
    """Return (summary_text, recent_messages) for building the next prompt.
    Pure read - never calls the model, so it's cheap enough to stay on the
    hot path. Folding overflow into the summary happens separately, see
    memory.manager.fold_overflow_into_summary."""
    session = session_repo.get(session_id)
    msgs = message_repo.list_for_session(session_id)
    keep_from = max(0, len(msgs) - keep_last)
    return session.summary, msgs[keep_from:]
