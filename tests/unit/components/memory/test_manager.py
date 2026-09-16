import pytest

from roleplay_agent.components.memory.context import get_context
from roleplay_agent.components.memory.manager import fold_overflow_into_summary
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import EmbeddingRepository, MessageRepository, SessionRepository

KEEP_LAST = 20


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return db


@pytest.fixture
def repos(db):
    return SessionRepository(db), MessageRepository(db)


@pytest.fixture
def embedding_repo(db):
    return EmbeddingRepository(db)


def make_summarizer():
    calls = []

    def summarize(prev_summary, chunk):
        calls.append((prev_summary, list(chunk)))
        return f"SUMMARY[{len(calls)}]"

    summarize.calls = calls
    return summarize


def test_fold_overflow_below_keep_last_is_a_noop(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST - 1):
        message_repo.add(session_id, "user", f"msg {i}")

    summarize = make_summarizer()
    folded = fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)

    assert folded is False
    assert summarize.calls == []
    assert session_repo.get(session_id).summary == ""


def test_fold_overflow_folds_messages_past_keep_last(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    total = KEEP_LAST + 5
    for i in range(total):
        message_repo.add(session_id, "user", f"msg {i}")

    summarize = make_summarizer()
    folded = fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)

    assert folded is True
    assert len(summarize.calls) == 1
    prev_summary, chunk = summarize.calls[0]
    assert prev_summary == ""
    assert len(chunk) == 5  # total - KEEP_LAST

    session = session_repo.get(session_id)
    assert session.summary == "SUMMARY[1]"
    assert session.summarized_count == 5

    summary, recent = get_context(session_repo, message_repo, session_id, KEEP_LAST)
    assert summary == "SUMMARY[1]"
    assert len(recent) == KEEP_LAST


def test_fold_overflow_is_idempotent_without_new_messages(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST + 5):
        message_repo.add(session_id, "user", f"msg {i}")

    summarize = make_summarizer()
    fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)
    fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)

    assert len(summarize.calls) == 1  # second call must not re-summarize


def test_fold_overflow_folds_again_after_more_messages(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST + 5):
        message_repo.add(session_id, "user", f"msg {i}")

    summarize = make_summarizer()
    fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)

    message_repo.add(session_id, "user", "one more")
    fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, summarize)

    assert len(summarize.calls) == 2
    prev_summary, chunk = summarize.calls[1]
    assert prev_summary == "SUMMARY[1]"
    assert len(chunk) == 1
    assert session_repo.get(session_id).summary == "SUMMARY[2]"


def test_fold_overflow_without_embedding_args_indexes_nothing(repos, embedding_repo):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST + 5):
        message_repo.add(session_id, "user", f"msg {i}")

    fold_overflow_into_summary(session_repo, message_repo, session_id, KEEP_LAST, make_summarizer())

    assert embedding_repo.search("g1", [1.0]) == []


def test_fold_overflow_embeds_chunk_before_summarizing_when_wired(repos, embedding_repo):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST + 5):
        message_repo.add(session_id, "user", f"msg {i}")

    embed_calls = []

    def embed_fn(text):
        embed_calls.append(text)
        return [1.0, 0.0]

    fold_overflow_into_summary(
        session_repo,
        message_repo,
        session_id,
        KEEP_LAST,
        make_summarizer(),
        embedding_repo=embedding_repo,
        embed_fn=embed_fn,
        game_id="g1",
    )

    assert len(embed_calls) == 1
    assert "msg 0" in embed_calls[0]  # the folded chunk's text, not the whole history

    [chunk] = embedding_repo.search("g1", [1.0, 0.0])
    assert chunk.session_id == session_id
    assert chunk.text == embed_calls[0]


def test_fold_overflow_skips_embedding_when_it_is_a_noop(repos, embedding_repo):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    for i in range(KEEP_LAST - 1):
        message_repo.add(session_id, "user", f"msg {i}")

    def fail_embed(text):
        raise AssertionError("embed_fn should not run when there's nothing to fold")

    folded = fold_overflow_into_summary(
        session_repo,
        message_repo,
        session_id,
        KEEP_LAST,
        make_summarizer(),
        embedding_repo=embedding_repo,
        embed_fn=fail_embed,
        game_id="g1",
    )

    assert folded is False
