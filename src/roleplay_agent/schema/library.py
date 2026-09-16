from pydantic import BaseModel


class LibraryEntry(BaseModel):
    """One "played game" card - a persona aggregated across every session
    you've had with it, for the Library grid."""

    id: str
    title: str
    character_name: str | None = None
    tags: list[str] = []
    cover_image: str | None = None
    session_count: int
    rounds: int
    played_seconds: float
    last_played: float
