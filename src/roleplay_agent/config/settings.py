from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# Deliberately cwd-based, not __file__-based: __file__ only points back at
# the repo when the package is pip-installed with -e (editable/dev mode).
# A regular `pip install .` (e.g. the Docker image) copies the package into
# site-packages, where climbing from __file__ no longer lands anywhere near
# the project root. The process is always started from the project root in
# every real usage (make dev/run, pytest, the Docker image's WORKDIR), so
# cwd is the one thing that's actually reliable here.
PROJECT_ROOT = Path.cwd()
CONFIGS_DIR = PROJECT_ROOT / "configs"


class ConfigError(RuntimeError):
    pass


def _load_yaml(name: str) -> dict:
    path = CONFIGS_DIR / name
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _yaml_defaults() -> dict:
    """configs/*.yaml set the checked-in baseline. Merged once at import
    time - `Settings` below reads its own (few, infra) keys off this dict
    per-field so normal pydantic-settings precedence (env var > .env file
    > default) still applies on top of it; `AppConfig` (below) is built
    from this same dict directly instead, with no env-override layer at
    all (see docs/ARCHITECTURE.md's "Config hygiene")."""
    merged: dict = {}
    merged.update(_load_yaml("app.yaml"))

    models = _load_yaml("models.yaml")
    if "keep_alive" in models:
        merged["keep_alive"] = models["keep_alive"]
    if "keep_last_messages" in models:
        merged["keep_last_messages"] = models["keep_last_messages"]
    if "default_num_ctx" in models:
        merged["default_num_ctx"] = models["default_num_ctx"]
    if "embedding_model" in models:
        merged["embedding_model"] = models["embedding_model"]
    if "enable_thinking" in models:
        merged["enable_thinking"] = models["enable_thinking"]

    research = _load_yaml("research.yaml")
    if "max_results" in research:
        merged["research_max_results"] = research["max_results"]
    if "user_agent" in research:
        merged["research_user_agent"] = research["user_agent"]

    transcript = _load_yaml("transcript.yaml")
    if "max_chars" in transcript:
        merged["transcript_max_chars"] = transcript["max_chars"]
    if "model_repo" in transcript:
        merged["stt_model_repo"] = transcript["model_repo"]
    if "quantize" in transcript:
        merged["stt_quantize"] = transcript["quantize"]

    tts = _load_yaml("tts.yaml")
    if "backend" in tts:
        merged["tts_backend"] = tts["backend"]
    if "max_chars" in tts:
        merged["tts_max_chars"] = tts["max_chars"]
    chatterbox = tts.get("chatterbox") or {}
    if "model_repo" in chatterbox:
        merged["tts_chatterbox_model_repo"] = chatterbox["model_repo"]
    if "quantize" in chatterbox:
        merged["tts_chatterbox_quantize"] = chatterbox["quantize"]
    qwen3 = tts.get("qwen3") or {}
    if "model_repo" in qwen3:
        merged["tts_qwen3_model_repo"] = qwen3["model_repo"]
    if "clone_model_repo" in qwen3:
        merged["tts_qwen3_clone_model_repo"] = qwen3["clone_model_repo"]

    logging_cfg = _load_yaml("logging.yaml")
    if "level" in logging_cfg:
        merged["log_level"] = logging_cfg["level"]

    return merged


_defaults = _yaml_defaults()


class Settings(BaseSettings):
    """Environment/infra config only - deployment-topology facts (which
    port to bind, where the data volume lives), the only things a
    `ROLEPLAY_<NAME>` env var or `.env` should ever be overriding. See
    `AppConfig` below for everything else - application behavior, sourced
    only from `configs/*.yaml`, no env-override mechanism at all."""

    host: str = _defaults.get("host", "127.0.0.1")
    port: int = _defaults.get("port", 8000)
    data_dir: Path = PROJECT_ROOT / "data"
    log_level: str = _defaults.get("log_level", "INFO")

    model_config = SettingsConfigDict(env_prefix="ROLEPLAY_", env_file=".env", extra="ignore")

    @property
    def games_dir(self) -> Path:
        return self.data_dir / "games"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def voice_samples_dir(self) -> Path:
        return self.data_dir / "voice_samples"


class AppConfig(BaseModel):
    """Application behavior - `configs/*.yaml` only, literally not a
    `BaseSettings` field, so e.g. `ROLEPLAY_KEEP_ALIVE` does nothing even
    if someone sets it. Split out from `Settings` structurally (a
    different base class, not just a naming convention) so that boundary
    can't quietly erode field by field the way it had before this split
    (see docs/ARCHITECTURE.md's "Config hygiene")."""

    model_config = SettingsConfigDict(extra="ignore")

    keep_alive: str = "30m"
    keep_last_messages: int = 20
    default_num_ctx: int = 8192
    # Only pulled/used when a game sets memory_recall: true (see games/models.py).
    # Required (no Python-level fallback) - a model name belongs in
    # configs/models.yaml, not duplicated as a string literal in code.
    embedding_model: str
    # Maps to langchain_ollama's ChatOllama `reasoning` field (Ollama's own
    # "think" option) - applied to every Ollama build_llm call, hosted
    # providers ignore it. None (unset in configs/models.yaml) means "don't
    # pass it at all", not "false" - a model/provider's own default stands.
    enable_thinking: bool | None = None
    # Powers the AI game-builder chat (A2) - filled in per-request by
    # api/routes/studio/game_builder.py's _resolved() (llm/capabilities.py's
    # resolve_builder_model), never configured: the builder always runs on
    # the same computed default a brand-new persona gets. None only until
    # that first resolution happens.
    builder_provider: str | None = None
    builder_model: str | None = None

    research_max_results: int = 4
    research_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    # Section A3 - caps a video/pasted transcript before it hits the draft
    # extraction prompt (see transcript/media.py).
    transcript_max_chars: int = 20000
    # Section A3/voice mode - local STT (see services/stt/stt.py). Any
    # Hugging Face `transformers` `automatic-speech-recognition`-pipeline-
    # compatible repo id - not pinned to one engine/model. Required (no
    # Python-level fallback), same "a model name belongs in configs/, not
    # duplicated as a string literal in code" reasoning as embedding_model
    # above - transformers itself is still optional (`pip install
    # '.[transcribe]'`), so this is read even if it's never installed; a
    # missing/unset value should never be the reason config loading fails,
    # only the reason a transcription request 422s. Device (cuda/mps/cpu)
    # is always auto-detected (services/stt/stt.py's _detect_device), never
    # a config field here.
    stt_model_repo: str
    # int8 | None. Dynamic PyTorch quantization of the pipeline model's
    # Linear layers - see services/stt/stt.py's get_pipeline. Optional
    # (unlike stt_model_repo above): quantization is a perf tweak, not
    # something the app requires a value for.
    stt_quantize: str | None = None

    # Section C - local TTS (see services/tts/tts.py). Which of the two
    # backends below is actually used - "chatterbox" or "qwen3". No
    # Python-level default: configs/tts.yaml always sets this, same
    # "required, not baked into code" reasoning as embedding_model above.
    tts_backend: str
    # chatterbox-tts is an optional dependency (`pip install
    # '.[tts-chatterbox]'`) - read even if it's never installed, since a
    # missing/unset value should never be the reason config loading fails.
    # Only actually required (see _REQUIRED_APP_CONFIG_KEYS below) when
    # tts_backend == "chatterbox".
    tts_chatterbox_model_repo: str | None = None
    tts_chatterbox_quantize: str | None = "int8"
    # mlx-audio itself is an optional dependency (`pip install '.[tts]'`,
    # Apple Silicon only). Only actually required when tts_backend ==
    # "qwen3" - see _REQUIRED_APP_CONFIG_KEYS below.
    tts_qwen3_model_repo: str | None = None
    # A second, much smaller checkpoint (~1-2GB quantized vs. the preset
    # model's ~6GB) that trades the curated preset speaker list for
    # real-time voice cloning from a reference clip - see
    # services/tts/tts.py's list_cloned_voices/synthesize. Not required
    # (unlike tts_qwen3_model_repo above): cloning is a zero-config opt-in
    # - drop a WAV in data/voice_samples/ and it's usable, nothing to
    # configure to make the preset voices keep working exactly as before.
    tts_qwen3_clone_model_repo: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-6bit"
    tts_max_chars: int = 1200


# Keys with no Python-level fallback - a model name belongs in configs/,
# never duplicated as a string literal in code, so a missing one is a
# clear startup error instead of a silently wrong default.
_REQUIRED_APP_CONFIG_KEYS = {
    "embedding_model": "configs/models.yaml",
    "stt_model_repo": "configs/transcript.yaml",
    "tts_backend": "configs/tts.yaml",
}

# Which extra key is required, per tts_backend value - see get_app_config().
# Not in _REQUIRED_APP_CONFIG_KEYS itself since which key is required
# depends on the backend chosen, not a fixed set. STT has no such table -
# it's a single always-on backend now, not a choice.
_TTS_BACKEND_REQUIRED_KEYS = {
    "chatterbox": ("tts_chatterbox_model_repo", "configs/tts.yaml (chatterbox.model_repo)"),
    "qwen3": ("tts_qwen3_model_repo", "configs/tts.yaml (qwen3.model_repo)"),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_app_config() -> AppConfig:
    required = dict(_REQUIRED_APP_CONFIG_KEYS)
    tts_backend_required = _TTS_BACKEND_REQUIRED_KEYS.get(_defaults.get("tts_backend"))
    if tts_backend_required:
        required[tts_backend_required[0]] = tts_backend_required[1]

    missing = [key for key in required if key not in _defaults]
    if missing:
        lines = "\n".join(f"  - {key} (in {required[key]})" for key in missing)
        raise ConfigError(f"Missing required config:\n{lines}")
    return AppConfig(**_defaults)
