from pydantic import BaseModel, ConfigDict, Field


class BuilderMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class CreateBuilderSessionRequest(BaseModel):
    title: str
    # Already known up front when this conversation is refining an
    # existing persona ("Edit with AI") - NULL for a "New persona" chat
    # until/unless a later save wires it up (see docs/ARCHITECTURE.md).
    game_id: str | None = None


class CreateBuilderSessionResponse(BaseModel):
    builder_session_id: str


class BuilderSessionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    game_id: str | None
    title: str
    created_at: float


class BuilderSessionMessagesResponse(BaseModel):
    session: BuilderSessionDetail
    messages: list[BuilderMessage]


class BuilderSessionChatRequest(BaseModel):
    message: str
    # The "here's the persona as it stands today" priming block for an
    # "Edit with AI" conversation - transient grounding context, prepended
    # to the LLM call but deliberately never persisted as a builder_messages
    # row (see api/routes/game_builder.py).
    context: str | None = None


class BuilderSessionDraftRequest(BaseModel):
    context: str | None = None


class TranscriptDraftRequest(BaseModel):
    transcript: str


class VideoDraftRequest(BaseModel):
    url: str


class GameDraft(BaseModel):
    """What the AI game-builder proposes from a conversation - deliberately
    a subset of Game's fields. Infra fields (provider/model/num_ctx/starter/
    etc.) are left to the editor's own defaults and adjustable by hand,
    since they're technical choices, not something a persona conversation
    naturally produces.

    Field descriptions matter here beyond documentation: they're what
    actually steers a local model's structured-output call toward full
    descriptive paragraphs instead of short placeholder labels (verified
    manually against this project's own default model)."""

    title: str = Field(description='A short, evocative title for the picker, e.g. "Stranded on a road trip"')
    tags: list[str] = Field(default_factory=list, description="2-4 short lowercase labels, e.g. [casual, drama]")
    persona: str = Field(
        description="A detailed paragraph describing who the AI plays: name, personality, speech "
        "style, what they want or avoid saying. Be specific about tone."
    )
    user_role: str = Field(
        description="A paragraph describing who the human is playing in this scene and their "
        "relationship to the AI's character."
    )
    script: str = Field(
        description="A paragraph describing the scene's background and a loose arc/beats the "
        "conversation might move through - not literal dialogue."
    )
    research_query: str = Field(default="", description="An optional web search seed for tone/style reference")
