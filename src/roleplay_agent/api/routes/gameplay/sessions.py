from fastapi import APIRouter, Depends, HTTPException, Response

from roleplay_agent.api.dependencies import (
    get_followup_repo,
    get_game_or_404,
    get_message_repo,
    get_session_or_404,
    get_session_repo,
)
from roleplay_agent.schema.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    MessageOut,
    RenameSessionRequest,
    ScheduledFollowupOut,
    SessionDetail,
    SessionMessagesResponse,
    SessionSummary,
)
from roleplay_agent.services.storage.models import Session
from roleplay_agent.services.storage.repositories import FollowupRepository, SessionRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=CreateSessionResponse)
def create_session(body: CreateSessionRequest):
    game = get_game_or_404(body.game_id)
    session_id = get_session_repo().create(body.game_id, game.title)
    return CreateSessionResponse(session_id=session_id, starter=game.starter)


@router.get("", response_model=list[SessionSummary])
def list_sessions():
    return [SessionSummary.model_validate(s) for s in get_session_repo().list_all()]


@router.get("/archived", response_model=list[SessionSummary])
def list_archived_sessions():
    return [SessionSummary.model_validate(s) for s in get_session_repo().list_archived()]


@router.post("/{session_id}/archive", response_model=SessionSummary)
def archive_session(
    session: Session = Depends(get_session_or_404),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    session_repo.archive(session.id)
    return SessionSummary.model_validate(session_repo.get(session.id))


@router.post("/{session_id}/unarchive", response_model=SessionSummary)
def unarchive_session(
    session: Session = Depends(get_session_or_404),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    session_repo.unarchive(session.id)
    return SessionSummary.model_validate(session_repo.get(session.id))


@router.patch("/{session_id}", response_model=SessionSummary)
def rename_session(
    body: RenameSessionRequest,
    session: Session = Depends(get_session_or_404),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    title = body.title.strip()
    if not title:
        raise HTTPException(422, "Title can't be empty.")
    session_repo.update_title(session.id, title)
    session.title = title
    return SessionSummary.model_validate(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session: Session = Depends(get_session_or_404),
    session_repo: SessionRepository = Depends(get_session_repo),
):
    session_repo.delete(session.id)
    return Response(status_code=204)


@router.get("/{session_id}/messages", response_model=SessionMessagesResponse)
def session_messages(session: Session = Depends(get_session_or_404)):
    messages = get_message_repo().list_for_session(session.id)
    return SessionMessagesResponse(
        session=SessionDetail.model_validate(session),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.get("/{session_id}/scheduled", response_model=ScheduledFollowupOut)
def scheduled_followup(
    session: Session = Depends(get_session_or_404),
    followup_repo: FollowupRepository = Depends(get_followup_repo),
):
    # Powers the countdown badge in ChatPage - the client polls this and
    # ticks down to fire_at locally rather than the server pushing anything.
    next_followup = followup_repo.next_for_session(session.id)
    return ScheduledFollowupOut(fire_at=next_followup.fire_at if next_followup else None)
