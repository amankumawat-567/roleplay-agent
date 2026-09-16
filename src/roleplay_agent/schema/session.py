from pydantic import BaseModel, ConfigDict


class CreateSessionRequest(BaseModel):
    game_id: str


class CreateSessionResponse(BaseModel):
    session_id: str
    starter: str


class RenameSessionRequest(BaseModel):
    title: str


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    game_id: str
    title: str
    created_at: float
    archived_at: float | None = None


class SessionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    game_id: str
    title: str
    summary: str
    summarized_count: int
    created_at: float


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    # "followup" for a scheduled check-back delivered in the background
    # (see storage.models.Message.kind) - lets the frontend render it
    # distinctly from a direct reply.
    kind: str = "reply"


class SessionMessagesResponse(BaseModel):
    session: SessionDetail
    messages: list[MessageOut]


class ScheduledFollowupOut(BaseModel):
    # None when nothing's pending - the UI's countdown badge just doesn't render.
    fire_at: float | None
