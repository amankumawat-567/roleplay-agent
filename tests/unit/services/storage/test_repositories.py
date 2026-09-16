import pytest

from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import (
    EmbeddingRepository,
    FollowupRepository,
    GameResearchRepository,
    MessageRepository,
    SessionRepository,
    SettingsRepository,
)


@pytest.fixture
def repos(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return SessionRepository(db), MessageRepository(db)


@pytest.fixture
def embedding_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return EmbeddingRepository(db)


@pytest.fixture
def followup_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return FollowupRepository(db)


@pytest.fixture
def settings_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return SettingsRepository(db)


@pytest.fixture
def game_research_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return GameResearchRepository(db)


def test_search_finds_matching_message(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Lighthouse Chat")
    message_repo.add(session_id, "user", "Tell me about the lighthouse keeper's routine.")

    results = message_repo.search("lighthouse")

    assert len(results) == 1
    assert results[0].session_id == session_id
    assert results[0].title == "Lighthouse Chat"
    assert "lighthouse" in results[0].snippet.lower()


def test_search_empty_query_returns_empty(repos):
    _, message_repo = repos
    assert message_repo.search("") == []
    assert message_repo.search("   ") == []


def test_archive_and_unarchive_move_session_between_lists(repos):
    session_repo, _ = repos
    session_id = session_repo.create("g1", "A session")

    session_repo.archive(session_id)
    assert [s.id for s in session_repo.list_all()] == []
    assert [s.id for s in session_repo.list_archived()] == [session_id]
    assert session_repo.get(session_id).archived_at is not None

    session_repo.unarchive(session_id)
    assert [s.id for s in session_repo.list_all()] == [session_id]
    assert [s.id for s in session_repo.list_archived()] == []
    assert session_repo.get(session_id).archived_at is None


def test_init_db_adds_archived_at_to_a_pre_existing_database(tmp_path):
    """A database created before A4 shipped has a `sessions` table with no
    `archived_at` column - init_db() must migrate it in place, not just
    rely on CREATE TABLE IF NOT EXISTS (which no-ops on an existing table)."""
    db_path = tmp_path / "legacy.db"
    db = Database(db_path)
    conn = db.connect()
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, game_id TEXT NOT NULL, title TEXT NOT NULL, "
        "summary TEXT NOT NULL DEFAULT '', summarized_count INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)"
    )
    conn.execute(
        "INSERT INTO sessions (id, game_id, title, created_at) VALUES ('s1', 'g1', 'Old session', 0.0)"
    )
    conn.commit()
    conn.close()

    db.init_db()

    session_repo = SessionRepository(db)
    assert session_repo.get("s1").archived_at is None
    session_repo.archive("s1")
    assert session_repo.get("s1").archived_at is not None


def test_search_no_matches_returns_empty(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    message_repo.add(session_id, "user", "hello there")

    assert message_repo.search("nonexistentword") == []


def test_search_requires_all_terms(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    message_repo.add(session_id, "user", "I love coffee in the morning")

    assert len(message_repo.search("coffee morning")) == 1
    assert message_repo.search("coffee evening") == []


def test_search_dedupes_to_one_result_per_session(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    message_repo.add(session_id, "user", "talking about dragons")
    message_repo.add(session_id, "assistant", "yes, dragons are great")

    results = message_repo.search("dragons")
    assert len(results) == 1
    assert results[0].session_id == session_id


def test_search_across_multiple_sessions(repos):
    session_repo, message_repo = repos
    s1 = session_repo.create("g1", "Session One")
    s2 = session_repo.create("g1", "Session Two")
    message_repo.add(s1, "user", "we talked about dragons")
    message_repo.add(s2, "user", "no dragons here, just cats")

    results = message_repo.search("dragons")
    assert {r.session_id for r in results} == {s1, s2}


def test_search_query_with_double_quote_does_not_raise(repos):
    # A raw double quote is FTS5 query syntax (starts a phrase) - unescaped,
    # it would raise sqlite3.OperationalError. This only asserts it's
    # handled gracefully, not that punctuation itself is searchable.
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    message_repo.add(session_id, "user", 'She said "hello" to me')

    message_repo.search('"hello"')


def test_embedding_search_returns_most_similar_first(embedding_repo):
    embedding_repo.add("g1", "s1", "about dragons", [1.0, 0.0])
    embedding_repo.add("g1", "s2", "about cats", [0.0, 1.0])

    [best] = embedding_repo.search("g1", [1.0, 0.0], top_k=1)
    assert best.text == "about dragons"
    assert best.session_id == "s1"


def test_embedding_search_scoped_to_game_id(embedding_repo):
    embedding_repo.add("g1", "s1", "g1's memory", [1.0, 0.0])
    embedding_repo.add("g2", "s2", "g2's memory", [1.0, 0.0])

    results = embedding_repo.search("g1", [1.0, 0.0], top_k=5)

    assert [r.text for r in results] == ["g1's memory"]


def test_embedding_search_respects_top_k(embedding_repo):
    for i in range(5):
        embedding_repo.add("g1", "s1", f"memory {i}", [1.0, 0.0])

    assert len(embedding_repo.search("g1", [1.0, 0.0], top_k=2)) == 2


def test_embedding_search_empty_when_nothing_stored(embedding_repo):
    assert embedding_repo.search("g1", [1.0, 0.0]) == []


def test_followup_due_returns_only_entries_at_or_before_now(followup_repo):
    followup_repo.schedule("s1", fire_at=100.0, reason="past")
    followup_repo.schedule("s1", fire_at=200.0, reason="future")

    due = followup_repo.due(now=150.0)

    assert [f.reason for f in due] == ["past"]


def test_followup_due_orders_by_fire_at_ascending(followup_repo):
    followup_repo.schedule("s1", fire_at=300.0, reason="third")
    followup_repo.schedule("s1", fire_at=100.0, reason="first")
    followup_repo.schedule("s1", fire_at=200.0, reason="second")

    due = followup_repo.due(now=1000.0)

    assert [f.reason for f in due] == ["first", "second", "third"]


def test_followup_delete_removes_it_from_due(followup_repo):
    followup_id = followup_repo.schedule("s1", fire_at=100.0, reason="gone soon")

    followup_repo.delete(followup_id)

    assert followup_repo.due(now=1000.0) == []


def test_followup_next_for_session_returns_the_soonest(followup_repo):
    followup_repo.schedule("s1", fire_at=300.0, reason="later")
    followup_repo.schedule("s1", fire_at=100.0, reason="soonest")
    followup_repo.schedule("s2", fire_at=50.0, reason="a different session")

    next_followup = followup_repo.next_for_session("s1")

    assert next_followup.reason == "soonest"


def test_followup_next_for_session_none_when_nothing_pending(followup_repo):
    assert followup_repo.next_for_session("s1") is None


def test_settings_get_returns_none_when_unset(settings_repo):
    assert settings_repo.get("profile") is None


def test_settings_set_then_get_round_trips(settings_repo):
    settings_repo.set("profile", '{"avatar_id": "a1"}')
    assert settings_repo.get("profile") == '{"avatar_id": "a1"}'


def test_settings_set_again_upserts_rather_than_erroring(settings_repo):
    settings_repo.set("default_provider", "ollama")
    settings_repo.set("default_provider", "openai")
    assert settings_repo.get("default_provider") == "openai"


def test_game_research_get_returns_none_when_unset(game_research_repo):
    assert game_research_repo.get("alpha") is None


def test_game_research_set_then_get_round_trips(game_research_repo):
    game_research_repo.set("alpha", "Uses casual phrasing.", sources_json='{"query": "x"}', fetched_at=123.0)

    row = game_research_repo.get("alpha")

    assert row.game_id == "alpha"
    assert row.notes == "Uses casual phrasing."
    assert row.sources_json == '{"query": "x"}'
    assert row.fetched_at == 123.0


def test_game_research_set_again_upserts_rather_than_duplicating(game_research_repo):
    game_research_repo.set("alpha", "First notes.")
    game_research_repo.set("alpha", "Second notes.")

    assert game_research_repo.get("alpha").notes == "Second notes."


def test_game_research_delete_removes_row_and_second_delete_is_a_no_op(game_research_repo):
    game_research_repo.set("alpha", "Some notes.")

    game_research_repo.delete("alpha")
    assert game_research_repo.get("alpha") is None

    game_research_repo.delete("alpha")  # harmless no-op
    assert game_research_repo.get("alpha") is None
