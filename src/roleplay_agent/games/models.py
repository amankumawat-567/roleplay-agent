from pydantic import BaseModel, Field


class Game(BaseModel):
    """A persona/scenario definition, validated at load time so a
    malformed data/games/<id>/game.yaml fails fast with a clear error
    instead of a KeyError mid-chat."""

    id: str
    title: str
    # The name shown anywhere the app refers to "who you're talking to"
    # (ChatPage's header, TypingIndicator) - distinct from `title`, which
    # stays the scenario/card display name ("Rooftop First Date" is a
    # scenario, not necessarily anyone's name). Falls back to `title` when
    # unset, so every game.yaml written before this field existed keeps
    # working exactly as before.
    character_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    provider: str = "ollama"
    model: str
    starter: str = "user"
    persona: str
    user_role: str
    script: str
    research_query: str = ""
    research_notes: str = ""
    num_ctx: int | None = None
    memory_recall: bool = False
    skills: list[str] = Field(default_factory=list)
    # One of llm.tts.SUPPORTED_VOICES, or None for no audio (the default -
    # every existing game.yaml behaves identically). Not validated against
    # that list here the way skills/provider aren't either - an editor-set
    # value is trusted, and POST /api/sessions/{id}/speak is where an
    # unrecognized voice actually surfaces as a clear error.
    voice: str | None = None
    # Filename only (e.g. "cover.jpg"), relative to data/games/<id>/ - set
    # exclusively by POST /api/games/{id}/cover, never authored by hand.
    # The frontend builds the actual URL from id + this filename.
    cover_image: str | None = None
