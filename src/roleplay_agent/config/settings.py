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
    if "builder_provider" in models:
        merged["builder_provider"] = models["builder_provider"]
    if "builder_model" in models:
        merged["builder_model"] = models["builder_model"]

    research = _load_yaml("research.yaml")
    if "max_results" in research:
        merged["research_max_results"] = research["max_results"]
    if "user_agent" in research:
        merged["research_user_agent"] = research["user_agent"]

    transcript = _load_yaml("transcript.yaml")
    if "max_chars" in transcript:
        merged["transcript_max_chars"] = transcript["max_chars"]
    if "whisper_model_size" in transcript:
        merged["whisper_model_size"] = transcript["whisper_model_size"]

    tts = _load_yaml("tts.yaml")
    if "model_repo" in tts:
        merged["tts_model_repo"] = tts["model_repo"]
    if "clone_model_repo" in tts:
        merged["tts_clone_model_repo"] = tts["clone_model_repo"]
    if "max_chars" in tts:
        merged["tts_max_chars"] = tts["max_chars"]

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
    # Powers the AI game-builder chat (A2) - independent of any persona's
    # own provider/model, so a stronger hosted model can be dedicated to
    # persona-building without moving the roleplay chat itself off Ollama.
    # None (unset in configs/models.yaml) means "compute it" - see
    # llm/capabilities.py's resolve_builder_model - not a hardcoded model
    # name in code.
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
    # faster-whisper model size for the audio-fallback path (transcript/
    # media.py) - only read when a URL has no captions. "base" is a
    # reasonable CPU-friendly default; faster-whisper itself is optional
    # (`pip install '.[transcribe]'`), so this is read even if it's never
    # installed - a missing/unset value should never be the reason config
    # loading fails.
    whisper_model_size: str = "base"

    # Section C - local TTS (see llm/tts.py). mlx-audio itself is an
    # optional dependency (`pip install '.[tts]'`, Apple Silicon only) -
    # read even if it's never installed, since a missing/unset value
    # should never be the reason config loading fails. Required, same
    # reasoning as embedding_model above.
    tts_model_repo: str
    # A second, much smaller checkpoint (~1-2GB quantized vs. the preset
    # model's ~6GB) that trades the curated preset speaker list for
    # real-time voice cloning from a reference clip - see llm/tts.py's
    # list_cloned_voices/synthesize. Not required (unlike tts_model_repo
    # above): cloning is a zero-config opt-in - drop a WAV in
    # data/voice_samples/ and it's usable, nothing to configure to make
    # the preset voices keep working exactly as before.
    tts_clone_model_repo: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-6bit"
    tts_max_chars: int = 1200


# Keys with no Python-level fallback - a model name belongs in configs/,
# never duplicated as a string literal in code, so a missing one is a
# clear startup error instead of a silently wrong default.
_REQUIRED_APP_CONFIG_KEYS = {
    "embedding_model": "configs/models.yaml",
    "tts_model_repo": "configs/tts.yaml",
}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_app_config() -> AppConfig:
    missing = [key for key in _REQUIRED_APP_CONFIG_KEYS if key not in _defaults]
    if missing:
        lines = "\n".join(f"  - {key} (in {_REQUIRED_APP_CONFIG_KEYS[key]})" for key in missing)
        raise ConfigError(f"Missing required config:\n{lines}")
    return AppConfig(**_defaults)
