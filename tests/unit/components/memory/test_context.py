import pytest

from roleplay_agent.components.memory.context import get_context
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import MessageRepository, SessionRepository

KEEP_LAST = 20


@pytest.fixture
def repos(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return SessionRepository(db), MessageRepository(db)


def test_get_context_never_calls_the_model(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST + 5):
        message_repo.add(session_id, "user", f"msg {i}")

    summary, recent = get_context(session_repo, message_repo, session_id, KEEP_LAST)

    assert summary == ""  # nothing folded yet, get_context doesn't fold
    assert len(recent) == KEEP_LAST  # always just the last KEEP_LAST, fold state aside


def test_get_context_below_keep_last_returns_everything(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST - 1):
        message_repo.add(session_id, "user", f"msg {i}")

    _, recent = get_context(session_repo, message_repo, session_id, KEEP_LAST)
    assert len(recent) == KEEP_LAST - 1
