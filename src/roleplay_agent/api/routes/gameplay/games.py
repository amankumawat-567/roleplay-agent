import shutil

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from roleplay_agent.api.dependencies import get_game_loader, get_game_or_404, get_game_research_repo, get_session_repo
from roleplay_agent.games.loader import VALID_ID_RE
from roleplay_agent.games.models import Game
from roleplay_agent.games.validator import GameConfigError, validate_game
from roleplay_agent.schema.game import GameCreateRequest, GameSummary, GameUpdateRequest

router = APIRouter(prefix="/api/games", tags=["games"])

# Content-type -> file extension. Whatever the browser reports for the
# picked file, not sniffed from bytes - single-user local tool, not a
# public upload surface.
_ALLOWED_COVER_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.get("", response_model=list[GameSummary])
def list_games():
    return [
        GameSummary(
            id=g.id,
            title=g.title,
            character_name=g.character_name,
            tags=g.tags,
            cover_image=g.cover_image,
            provider=g.provider,
            model=g.model,
        )
        for g in get_game_loader().list_all()
    ]


@router.get("/{game_id}", response_model=Game)
def get_game(game: Game = Depends(get_game_or_404)):
    return game


@router.post("", response_model=Game, status_code=201)
def create_game(body: GameCreateRequest):
    loader = get_game_loader()
    game_id = body.id or loader.slug_for_title(body.title)
    if not VALID_ID_RE.fullmatch(game_id):
        raise HTTPException(422, f"Invalid game id: {game_id!r}")
    if loader.exists(game_id):
        raise HTTPException(409, f"Game '{game_id}' already exists")

    try:
        game = validate_game(game_id, body.model_dump(exclude={"id"}))
    except GameConfigError as exc:
        raise HTTPException(422, str(exc))
    loader.save(game)
    return loader.load(game_id)  # re-read so research_notes (if any) is merged in


@router.put("/{game_id}", response_model=Game)
def update_game(game_id: str, body: GameUpdateRequest):
    loader = get_game_loader()
    if not loader.exists(game_id):
        raise HTTPException(404, f"No such game: {game_id}")

    try:
        game = validate_game(game_id, body.model_dump())
    except GameConfigError as exc:
        raise HTTPException(422, str(exc))
    # GameUpdateRequest has no cover_image field - covers are managed only
    # by upload_cover below, so a plain field edit must not wipe one out.
    game.cover_image = loader.load(game_id).cover_image
    loader.save(game)
    return loader.load(game_id)  # re-read so research_notes (if any) is merged in


@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: str):
    loader = get_game_loader()
    if not loader.exists(game_id):
        raise HTTPException(404, f"No such game: {game_id}")

    # Cascade first (sessions/messages/embeddings/follow-ups/research), then
    # the on-disk game directory - if the process dies between the two, the
    # game is still gone from every listing/search surface, just with a
    # harmless leftover directory rather than a DB row pointing nowhere.
    get_session_repo().delete_for_game(game_id)
    get_game_research_repo().delete(game_id)
    shutil.rmtree(loader.games_dir / game_id)
    return Response(status_code=204)


@router.post("/{game_id}/cover", response_model=Game)
def upload_cover(game_id: str, file: UploadFile = File(...)):
    loader = get_game_loader()
    if not loader.exists(game_id):
        raise HTTPException(404, f"No such game: {game_id}")

    ext = _ALLOWED_COVER_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(422, f"Unsupported image type: {file.content_type!r}")

    game_dir = loader.games_dir / game_id
    for existing in game_dir.glob("cover.*"):
        existing.unlink()
    dest = game_dir / f"cover{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    game = loader.load(game_id)
    game.cover_image = dest.name
    loader.save(game)
    return loader.load(game_id)
