#!/usr/bin/env python3
"""Import legacy flat configs/<id>.yaml persona files (pre-restructure) into
data/games/<id>/game.yaml (+ the `game_research` sqlite table). Idempotent -
skips any game_id that already has a data/games/<id>/ directory, so it's
safe to re-run.

Only files that actually look like a persona config (have "persona" and
"script" keys) are treated as games - configs/app.yaml, models.yaml,
research.yaml, and logging.yaml are app-level settings, not games, and are
always skipped even though they also live under configs/.
"""
from pathlib import Path

import yaml

from roleplay_agent.games.yaml_io import dump_yaml
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import GameResearchRepository

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CONFIGS_DIR = REPO_ROOT / "configs"
GAMES_DIR = REPO_ROOT / "data" / "games"

GAME_FIELDS = {"title", "tags", "model", "starter", "persona", "user_role", "script", "research_query", "num_ctx"}


def _looks_like_game(data: dict) -> bool:
    return "persona" in data and "script" in data


def migrate_one(path: Path, research_repo: GameResearchRepository) -> str:
    game_id = path.stem
    dest_dir = GAMES_DIR / game_id
    if dest_dir.exists():
        return f"skip {game_id} (already migrated)"

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    if not _looks_like_game(data):
        return f"skip {path.name} (not a game config)"

    research_notes = data.pop("research_notes", "")
    game_data = {k: v for k, v in data.items() if k in GAME_FIELDS}

    dest_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(game_data, dest_dir / "game.yaml")
    if research_notes:
        research_repo.set(game_id, research_notes)

    return f"migrated {game_id}"


def main() -> None:
    if not LEGACY_CONFIGS_DIR.exists():
        print("No legacy configs/ directory found - nothing to migrate.")
        return

    # This script runs standalone, not through the FastAPI dependency graph
    # - it builds its own Database/GameResearchRepository the same way
    # api/dependencies.py's get_database()/get_game_research_repo() do.
    db = Database(REPO_ROOT / "data" / "app.db")
    db.init_db()
    research_repo = GameResearchRepository(db)

    for path in sorted(LEGACY_CONFIGS_DIR.glob("*.yaml")):
        print(migrate_one(path, research_repo))


if __name__ == "__main__":
    main()
