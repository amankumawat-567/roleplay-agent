from pydantic import BaseModel, Field


class GameSummary(BaseModel):
    id: str
    title: str
    character_name: str | None = None
    tags: list[str] = []
    cover_image: str | None = None
    # Carried on the list response (not just GET /api/games/{id}'s full
    # Game) so the frontend can gate section F's voice-mode switch - via
    # llm.capabilities.has_capability against the capability cache - without
    # a per-persona fetch. Cheap: both already live on every game.yaml.
    provider: str
    model: str


class GameCreateRequest(BaseModel):
    """Fields for a new Game. `id` is optional - derived from `title` via
    GameLoader.slug_for_title when omitted. `research_notes` is deliberately
    absent: it's written separately by the research pipeline, never as part
    of an authored game.yaml."""

    id: str | None = None
    title: str
    character_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    provider: str = "ollama"
    model: str
    starter: str = "user"
    persona: str
    user_role: str
    script: str
    research_query: str = ""
    num_ctx: int | None = None
    memory_recall: bool = False
    skills: list[str] = Field(default_factory=list)
    voice: str | None = None


class GameUpdateRequest(BaseModel):
    title: str
    character_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    provider: str = "ollama"
    model: str
    starter: str = "user"
    persona: str
    user_role: str
    script: str
    research_query: str = ""
    num_ctx: int | None = None
    memory_recall: bool = False
    skills: list[str] = Field(default_factory=list)
    voice: str | None = None
