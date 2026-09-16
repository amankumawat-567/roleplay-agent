import sqlite3
from pathlib import Path


class Database:
    """Thin sqlite connection helper - one short-lived connection per call.
    Plenty for a single-user local app; see repositories.py for the actual
    queries."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # WAL + NORMAL: this app was running on sqlite's default DELETE
        # journal mode with no pragmas at all, meaning every commit did a
        # full fsync. A standard, low-risk win for a write-per-turn
        # workload like this one.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def init_db(self) -> None:
        conn = self.connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                summarized_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                archived_at REAL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                kind TEXT NOT NULL DEFAULT 'reply'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content, session_id UNINDEXED, content='messages', content_rowid='id'
            );
            -- messages are only ever inserted or deleted wholesale (session
            -- delete cascades here - see SessionRepository.delete), never
            -- updated, so insert + delete triggers are enough to keep this
            -- external-content FTS table in sync.
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, session_id)
                VALUES (new.id, new.content, new.session_id);
            END;
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content, session_id)
                VALUES ('delete', old.id, old.content, old.session_id);
            END;
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                text TEXT NOT NULL,
                vector TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_embeddings_game_id ON embeddings (game_id);
            CREATE TABLE IF NOT EXISTS pending_followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                fire_at REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pending_followups_fire_at ON pending_followups (fire_at);
            -- The AI Studio builder chat's own session/message pair -
            -- deliberately separate from sessions/messages above, not a
            -- nullable game_id + kind discriminator bolted on: a builder
            -- conversation is a chat about designing a persona, not a
            -- chat with one, and the roleplay tables already have several
            -- things (FTS, Library stats, memory embeddings) that assume
            -- every session row is a played persona chat.
            CREATE TABLE IF NOT EXISTS builder_sessions (
                id TEXT PRIMARY KEY,
                game_id TEXT,
                title TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS builder_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                builder_session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_builder_messages_session_id ON builder_messages (builder_session_id);
            -- Small key/value store backing the single-user profile and the
            -- model/provider discovery caches (see SettingsRepository) -
            -- folds data/profile.json + data/cache/*.json into the db.
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            -- One row per persona's research pass - folds
            -- data/games/<id>/research.yaml + data/research/<id>/ into the
            -- db (see GameResearchRepository).
            CREATE TABLE IF NOT EXISTS game_research (
                game_id TEXT PRIMARY KEY,
                notes TEXT NOT NULL DEFAULT '',
                sources_json TEXT NOT NULL DEFAULT '',
                fetched_at REAL
            );
            """
        )
        self._add_column_if_missing(conn, "sessions", "archived_at", "REAL")
        self._add_column_if_missing(conn, "messages", "kind", "TEXT NOT NULL DEFAULT 'reply'")
        conn.commit()
        conn.close()

    def _add_column_if_missing(self, conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
        """`CREATE TABLE IF NOT EXISTS` above only covers a brand-new
        database - a column added to an existing table's schema (like
        `archived_at`, added for A4) needs its own migration so a
        database created before that change still gets it."""
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
