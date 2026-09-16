import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ollama import ResponseError

from roleplay_agent.agents.game_play.followups import run_followup_loop
from roleplay_agent.api.dependencies import (
    get_agent,
    get_database,
    get_followup_repo,
    get_game_loader,
    get_message_repo,
    get_session_repo,
    get_tts_pool,
)
from roleplay_agent.api.routes.gameplay import chat, games, library, search, sessions
from roleplay_agent.api.routes.studio import game_builder, research, skills
from roleplay_agent.api.routes.system import health, models, profile, voices
from roleplay_agent.components.observability.logging import logger, setup_logging
from roleplay_agent.config.settings import get_app_config, get_settings
from roleplay_agent.services import tts as tts_module
from roleplay_agent.services.llm.errors import describe_llm_error
from roleplay_agent.services.llm.providers import ProviderConfigError

settings = get_settings()
# Eagerly, at import time (not on first request) - a missing required key
# (embedding_model/tts_model_repo) should fail the process at startup, not
# surface as a confusing error mid-conversation later.
app_config = get_app_config()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Section B2's poll loop for scheduled follow-ups (see agent.followups)
    # - started here rather than in a route so it runs for the whole life
    # of the process, independent of any one request.
    task = asyncio.create_task(
        run_followup_loop(
            get_followup_repo(),
            get_session_repo(),
            get_message_repo(),
            get_game_loader(),
            get_agent(),
            app_config.default_num_ctx,
        )
    )
    try:
        yield
    finally:
        task.cancel()
        # Section C's TTS worker process (see llm/tts.py) - only ever
        # actually spawned once a voice request comes in, but shut down
        # unconditionally here so a dev server reload/restart never leaves
        # one dangling. synthesize_stream()'s own SyncManager process (a
        # second, separate spawned process, backing its cross-process
        # queue) is a no-op to shut down if streaming TTS was never used.
        get_tts_pool().shutdown(wait=False, cancel_futures=True)
        tts_module.shutdown_tts_manager()


app = FastAPI(title="Roleplay Agent", lifespan=lifespan)
get_database().init_db()

app.include_router(health.router)
app.include_router(games.router)
app.include_router(game_builder.router)
app.include_router(models.router)
app.include_router(research.router)
app.include_router(search.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(library.router)
app.include_router(profile.router)
app.include_router(voices.router)

# Uploaded game-card cover images (see POST /api/games/{id}/cover) - served
# straight off data/games/<id>/cover.* rather than copied anywhere else.
settings.games_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/games", StaticFiles(directory=settings.games_dir), name="game_media")

# Section C's voice preview clips (dev-ui's AudioPage) - checked-in sample
# audio under data/voice_samples/, same "served straight off data/" pattern
# as game cover images above, not copied into the frontend's own public/.
settings.voice_samples_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/voice-samples", StaticFiles(directory=settings.voice_samples_dir), name="voice_samples")


@app.exception_handler(httpx.TransportError)
async def ollama_unreachable_handler(request: Request, exc: httpx.TransportError):
    logger.error("Ollama unreachable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": describe_llm_error(exc)})


@app.exception_handler(ResponseError)
async def ollama_response_error_handler(request: Request, exc: ResponseError):
    logger.error("Ollama error: %s", exc)
    return JSONResponse(status_code=502, content={"detail": describe_llm_error(exc)})


@app.exception_handler(ProviderConfigError)
async def provider_config_error_handler(request: Request, exc: ProviderConfigError):
    # A bad/missing provider setup (e.g. no API key exported yet) - a config
    # problem, not a runtime service outage, hence 422 rather than 502/503.
    logger.error("Provider config error: %s", exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})

# cwd-based, not __file__-based - see the comment on PROJECT_ROOT in
# config/settings.py for why. The built dev-ui/ SPA stays buildable/
# deployable independently of the backend package either way.
UI_DIST_DIR = Path.cwd() / "dev-ui" / "dist"
if UI_DIST_DIR.exists():
    # A real static file (dist/assets/*.js, dist/profile-avatar.svg, ...)
    # is served as-is; anything else - a client-side route like `/explore`
    # with no matching file on disk, which a plain `StaticFiles(html=True)`
    # mount 404s on - falls back to index.html so React Router can take
    # over client-side (see docs/ARCHITECTURE.md's "SPA fallback route").
    #
    # Deliberately **not** `app.mount("/", StaticFiles(...))` + a separate
    # catch-all route registered after it: verified live that Starlette
    # commits to the first *matching* route, not the first one that
    # succeeds - a `Mount("/")` matches every path (mount matching is
    # prefix-based, and "/" is a prefix of everything), so it intercepts
    # every request before a route registered after it is ever reached,
    # even one the mount itself would 404 on. One catch-all route, doing
    # both jobs, is the only thing that actually works here.
    _index_html = (UI_DIST_DIR / "index.html").read_text()
    _ui_dist_dir_resolved = UI_DIST_DIR.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str):
        # A mistyped or removed /api/... or /media/... path should still be
        # a real 404, not the SPA shell with a 200 - registration order
        # only keeps this catch-all from *out-competing* those routers for
        # a path they actually claim, it doesn't stop this route from
        # matching one they don't (every real API path is only reachable
        # this way if literally nothing else claimed it first).
        if full_path.startswith("api/") or full_path.startswith("media/"):
            raise HTTPException(404)

        candidate = (UI_DIST_DIR / full_path).resolve()
        # candidate.is_file() also rejects a directory URL like "/" itself
        # (full_path == ""), which correctly falls through to index.html
        # below rather than needing StaticFiles' own directory-index logic.
        if candidate.is_file() and _ui_dist_dir_resolved in candidate.parents:
            return FileResponse(candidate)
        return HTMLResponse(_index_html)
else:
    logger.warning("dev-ui/dist not found - run `cd dev-ui && npm install && npm run build`. Serving API only.")
