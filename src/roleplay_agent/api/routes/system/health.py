import ollama
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    try:
        # A cheap local-model listing, not a generation call - confirms
        # Ollama is actually reachable without any inference cost.
        models = ollama.Client().list()
        return {"status": "ok", "ollama": "reachable", "models": [m.model for m in models.models]}
    except Exception as exc:
        # Deliberately broad: a health check's job is "tell me if anything
        # is wrong," not to enumerate every failure mode.
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "ollama": "unreachable", "detail": str(exc)},
        )
