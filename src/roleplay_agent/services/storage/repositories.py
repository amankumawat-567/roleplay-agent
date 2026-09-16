import json
import math
import time
import uuid

from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.models import (
    BuilderSession,
    EmbeddingChunk,
    GameResearch,
    Message,
    PendingFollowup,
    SearchResult,
    Session,
)

# Raw FTS hits fetched before dedup by session - a generous bound, not a
# tuning knob: single-user local scale never gets close to it.
_MAX_RAW_MATCHES = 200


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, game_id: str, title: str) -> str:
        session_id = uuid.uuid4().hex[:12]
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO sessions (id, game_id, title, created_at) VALUES (?, ?, ?, ?)",
            (session_id, game_id, title, time.time()),
        )
        conn.commit()
        conn.close()
        return session_id

    def list_all(self) -> list[Session]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT id, game_id, title, created_at, archived_at FROM sessions "
            "WHERE archived_at IS NULL ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [Session(**dict(r)) for r in rows]

    def list_archived(self) -> list[Session]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT id, game_id, title, created_at, archived_at FROM sessions "
            "WHERE archived_at IS NOT NULL ORDER BY archived_at DESC"
        ).fetchall()
        conn.close()
        return [Session(**dict(r)) for r in rows]

    def archive(self, session_id: str) -> None:
        conn = self.db.connect()
        conn.execute("UPDATE sessions SET archived_at = ? WHERE id = ?", (time.time(), session_id))
        conn.commit()
        conn.close()

    def unarchive(self, session_id: str) -> None:
        conn = self.db.connect()
        conn.execute("UPDATE sessions SET archived_at = NULL WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    def get(self, session_id: str) -> Session | None:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        return Session(**dict(row)) if row else None

    def delete(self, session_id: str) -> None:
        """Removes a session and everything scoped to it - messages (the
        messages_ad trigger keeps messages_fts in sync), long-term memory
        chunks, and any still-pending B2 follow-up. One connection so a
        crash mid-delete can't leave the FTS index or embeddings orphaned
        pointing at a session that no longer exists."""
        conn = self.db.connect()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM embeddings WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM pending_followups WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    def delete_for_game(self, game_id: str) -> None:
        """Bulk version of delete() for every session belonging to one
        game - used by DELETE /api/games/{game_id} so removing a persona
        doesn't leave orphaned sessions/messages/embeddings/follow-ups
        behind. Same one-connection rationale as delete()."""
        conn = self.db.connect()
        conn.execute(
            "DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute("DELETE FROM embeddings WHERE game_id = ?", (game_id,))
        conn.execute(
            "DELETE FROM pending_followups WHERE session_id IN (SELECT id FROM sessions WHERE game_id = ?)",
            (game_id,),
        )
        conn.execute("DELETE FROM sessions WHERE game_id = ?", (game_id,))
        conn.commit()
        conn.close()

    def update_title(self, session_id: str, title: str) -> None:
        conn = self.db.connect()
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()
        conn.close()

    def update_summary(self, session_id: str, summary: str, summarized_count: int) -> None:
        conn = self.db.connect()
        conn.execute(
            "UPDATE sessions SET summary = ?, summarized_count = ? WHERE id = ?",
            (summary, summarized_count, session_id),
        )
        conn.commit()
        conn.close()

    def library_stats(self) -> dict[str, dict]:
        """Per-persona aggregates for the Library grid - session count,
        total rounds (user turns) and played time (each session's
        first-to-last message span, summed) across every session, plus
        the most recent session's start time. Computed in Python rather
        than SQL to stay readable at single-user scale (see the module
        docstring precedent in EmbeddingRepository.search)."""
        conn = self.db.connect()
        sessions = conn.execute(
            "SELECT id, game_id, title, created_at FROM sessions ORDER BY created_at ASC"
        ).fetchall()
        messages = conn.execute(
            "SELECT session_id, role, created_at FROM messages ORDER BY id ASC"
        ).fetchall()
        conn.close()

        messages_by_session: dict[str, list] = {}
        for m in messages:
            messages_by_session.setdefault(m["session_id"], []).append(m)

        stats: dict[str, dict] = {}
        for s in sessions:
            entry = stats.setdefault(
                s["game_id"],
                {"title": s["title"], "session_count": 0, "rounds": 0, "played_seconds": 0.0, "last_played": 0.0},
            )
            # Sessions are visited oldest-first, so this always ends up
            # holding the most recent session's title - the fallback used
            # if the persona's own game.yaml has since been deleted.
            entry["title"] = s["title"]
            entry["session_count"] += 1
            entry["last_played"] = max(entry["last_played"], s["created_at"])

            session_messages = messages_by_session.get(s["id"], [])
            entry["rounds"] += sum(1 for m in session_messages if m["role"] == "user")
            if len(session_messages) >= 2:
                entry["played_seconds"] += session_messages[-1]["created_at"] - session_messages[0]["created_at"]

        return stats


class MessageRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, session_id: str, role: str, content: str, kind: str = "reply") -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at, kind) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, time.time(), kind),
        )
        conn.commit()
        conn.close()

    def count_role(self, session_id: str, role: str) -> int:
        """Used by A0's auto-titling to detect "this was the session's first
        user message" without loading every message's content - a bare
        COUNT is cheap enough per-turn at single-user scale that it doesn't
        need a dedicated `sessions.title_set` flag."""
        conn = self.db.connect()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id = ? AND role = ?",
            (session_id, role),
        ).fetchone()
        conn.close()
        return row["n"]

    def list_for_session(self, session_id: str) -> list[Message]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT role, content, created_at, kind FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        conn.close()
        return [Message(**dict(r)) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Full-text search over message content, deduplicated to one
        (best-matching) result per session so it can be merged straight
        into a session list."""
        terms = query.split()
        if not terms:
            return []
        match_query = " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)

        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT m.session_id AS session_id, s.title AS title,
                   snippet(messages_fts, 0, '', '', '…', 12) AS snippet
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match_query, _MAX_RAW_MATCHES),
        ).fetchall()
        conn.close()

        results: list[SearchResult] = []
        seen_sessions: set[str] = set()
        for row in rows:
            if row["session_id"] in seen_sessions:
                continue
            seen_sessions.add(row["session_id"])
            results.append(SearchResult(**dict(row)))
            if len(results) >= limit:
                break
        return results


class BuilderSessionRepository:
    """The AI Studio builder chat's own session store - see
    docs/ARCHITECTURE.md's "AI Studio gets its own persisted session type"
    for why this is a genuinely separate pair of tables rather than the
    roleplay `sessions`/`messages` above with a discriminator column."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str, game_id: str | None) -> str:
        session_id = uuid.uuid4().hex[:12]
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO builder_sessions (id, game_id, title, created_at) VALUES (?, ?, ?, ?)",
            (session_id, game_id, title, time.time()),
        )
        conn.commit()
        conn.close()
        return session_id

    def get(self, session_id: str) -> BuilderSession | None:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM builder_sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        return BuilderSession(**dict(row)) if row else None


class BuilderMessageRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, builder_session_id: str, role: str, content: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO builder_messages (builder_session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (builder_session_id, role, content, time.time()),
        )
        conn.commit()
        conn.close()

    def list_for_session(self, builder_session_id: str) -> list[Message]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT role, content, created_at FROM builder_messages WHERE builder_session_id = ? ORDER BY id ASC",
            (builder_session_id,),
        ).fetchall()
        conn.close()
        return [Message(**dict(r)) for r in rows]


class FollowupRepository:
    """Durable scheduling for the `schedule_followup` skill (section B2) -
    a plain table + poll loop (see agent.followups) rather than a job-queue
    dependency, so a scheduled check-back survives a server restart:
    due-ness is computed from the stored fire_at, never from anything held
    only in memory."""

    def __init__(self, db: Database):
        self.db = db

    def schedule(self, session_id: str, fire_at: float, reason: str) -> int:
        conn = self.db.connect()
        cur = conn.execute(
            "INSERT INTO pending_followups (session_id, fire_at, reason, created_at) VALUES (?, ?, ?, ?)",
            (session_id, fire_at, reason, time.time()),
        )
        conn.commit()
        followup_id = cur.lastrowid
        conn.close()
        return followup_id

    def due(self, now: float) -> list[PendingFollowup]:
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT id, session_id, fire_at, reason, created_at FROM pending_followups "
            "WHERE fire_at <= ? ORDER BY fire_at ASC",
            (now,),
        ).fetchall()
        conn.close()
        return [PendingFollowup(**dict(r)) for r in rows]

    def delete(self, followup_id: int) -> None:
        conn = self.db.connect()
        conn.execute("DELETE FROM pending_followups WHERE id = ?", (followup_id,))
        conn.commit()
        conn.close()

    def next_for_session(self, session_id: str) -> PendingFollowup | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT id, session_id, fire_at, reason, created_at FROM pending_followups "
            "WHERE session_id = ? ORDER BY fire_at ASC LIMIT 1",
            (session_id,),
        ).fetchone()
        conn.close()
        return PendingFollowup(**dict(row)) if row else None


class SettingsRepository:
    """Small key/value store backing the single-user profile and the
    model/provider discovery caches (llm/capabilities.py) - see
    docs/ARCHITECTURE.md's "Config hygiene"/"Discovery, live, on a TTL"
    for why these used to be separate JSON files and now aren't."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str) -> str | None:
        conn = self.db.connect()
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()


class GameResearchRepository:
    """One row per persona's research pass - replaces the old
    data/games/<id>/research.yaml + data/research/<id>/ files. See
    games/loader.py's GameLoader and agents/research/researcher.py."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, game_id: str) -> GameResearch | None:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM game_research WHERE game_id = ?", (game_id,)).fetchone()
        conn.close()
        return GameResearch(**dict(row)) if row else None

    def set(self, game_id: str, notes: str, sources_json: str = "", fetched_at: float | None = None) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO game_research (game_id, notes, sources_json, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(game_id) DO UPDATE SET notes = excluded.notes, "
            "sources_json = excluded.sources_json, fetched_at = excluded.fetched_at",
            (game_id, notes, sources_json, fetched_at),
        )
        conn.commit()
        conn.close()

    def delete(self, game_id: str) -> None:
        conn = self.db.connect()
        conn.execute("DELETE FROM game_research WHERE game_id = ?", (game_id,))
        conn.commit()
        conn.close()


class EmbeddingRepository:
    """Long-term memory store for section F's semantic recall - a chunk per
    background fold (see memory.manager.fold_overflow_into_summary), scored
    with a brute-force cosine scan. Simplest thing that works at
    single-user scale (hundreds to low-thousands of chunks); reach for a
    real vector index (e.g. sqlite-vec) only if that stops being true."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, game_id: str, session_id: str, text: str, vector: list[float]) -> None:
        conn = self.db.connect()
        conn.execute(
            "INSERT INTO embeddings (game_id, session_id, text, vector, created_at) VALUES (?, ?, ?, ?, ?)",
            (game_id, session_id, text, json.dumps(vector), time.time()),
        )
        conn.commit()
        conn.close()

    def search(self, game_id: str, query_vector: list[float], top_k: int = 3) -> list[EmbeddingChunk]:
        """Scoped to one game_id so one persona's memories never bleed into
        a different persona's conversation - deliberately not scoped to a
        single session, since recalling something from an *earlier*
        session with the same persona is the point of long-term memory."""
        conn = self.db.connect()
        rows = conn.execute(
            "SELECT session_id, text, vector, created_at FROM embeddings WHERE game_id = ?",
            (game_id,),
        ).fetchall()
        conn.close()

        scored = [(_cosine_similarity(query_vector, json.loads(row["vector"])), row) for row in rows]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            EmbeddingChunk(session_id=row["session_id"], text=row["text"], created_at=row["created_at"])
            for _, row in scored[:top_k]
        ]
