from dataclasses import dataclass


@dataclass
class Message:
    role: str
    content: str
    created_at: float = 0.0
    # "followup" for an assistant message delivered by a scheduled
    # check-back (agent.followups) rather than a direct reply to something
    # the user just sent - lets the UI render it distinctly (ChatBubble.tsx)
    # so a check-in reads as its own event, not just another reply.
    kind: str = "reply"


@dataclass
class Session:
    id: str
    game_id: str
    title: str
    summary: str = ""
    summarized_count: int = 0
    created_at: float = 0.0
    archived_at: float | None = None


@dataclass
class SearchResult:
    session_id: str
    title: str
    snippet: str


@dataclass
class EmbeddingChunk:
    session_id: str
    text: str
    created_at: float = 0.0


@dataclass
class PendingFollowup:
    id: int
    session_id: str
    fire_at: float
    reason: str
    created_at: float = 0.0


@dataclass
class GameResearch:
    """One persona's research pass - see GameResearchRepository and
    games/loader.py's GameLoader/agents/research/researcher.py."""

    game_id: str
    notes: str
    sources_json: str = ""
    fetched_at: float | None = None


@dataclass
class BuilderSession:
    """The AI Studio builder chat's own session record - deliberately not
    the roleplay `Session` above (see docs/ARCHITECTURE.md's "AI Studio
    gets its own persisted session type" for why a separate table, not a
    shared one with a flag)."""

    id: str
    game_id: str | None
    title: str
    created_at: float = 0.0
