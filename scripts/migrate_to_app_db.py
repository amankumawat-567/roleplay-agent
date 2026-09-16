#!/usr/bin/env python3
"""One-shot migration: folds every remaining JSON/YAML runtime file into
the sqlite db (Part 2 of the multi-part refactor). Hardcodes the old
relative paths directly rather than depending on Settings properties that
no longer exist in code by the time this runs:

  data/profile.json                        -> app_settings["profile"]
  data/cache/default_provider.json         -> app_settings["default_provider"]
  data/cache/model_capabilities.json       -> app_settings["model_capabilities"]
  data/games/<id>/research.yaml            -> game_research row per game_id
    + data/research/<id>/sources.json/raw/*.txt (folded into sources_json)
  data/db/sessions.db                      -> renamed to data/app.db

Then deletes the now-obsolete data/db/, data/cache/, data/research/,
data/profile.json, data/sessions/, and every research.yaml. Not idempotent
by design - a one-shot tool for this exact transition, not a permanent
maintenance script (unlike scripts/cleanup.py/scripts/seed_games.py).
"""
import json
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

OLD_DB_DIR = DATA_DIR / "db"
OLD_DB_PATH = OLD_DB_DIR / "sessions.db"
NEW_DB_PATH = DATA_DIR / "app.db"
OLD_CACHE_DIR = DATA_DIR / "cache"
OLD_RESEARCH_DIR = DATA_DIR / "research"
OLD_PROFILE_PATH = DATA_DIR / "profile.json"
OLD_SESSIONS_DIR = DATA_DIR / "sessions"
GAMES_DIR = DATA_DIR / "games"


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from roleplay_agent.services.storage.database import Database
    from roleplay_agent.services.storage.repositories import GameResearchRepository, SettingsRepository

    summary = {
        "profile": False,
        "default_provider": False,
        "model_capabilities": False,
        "game_research_rows": 0,
        "db_moved": False,
    }

    # 1. Open the *old* db path directly and run the new DDL against it -
    # reuse init_db() rather than hand-rolling the CREATE TABLE statements.
    if OLD_DB_PATH.exists():
        old_db = Database(OLD_DB_PATH)
        old_db.init_db()
        settings_repo = SettingsRepository(old_db)
        research_repo = GameResearchRepository(old_db)
    else:
        # No prior db at all (fresh checkout) - operate straight against
        # the new path so steps 2-5 below still have somewhere to write.
        new_db = Database(NEW_DB_PATH)
        new_db.init_db()
        settings_repo = SettingsRepository(new_db)
        research_repo = GameResearchRepository(new_db)

    # 2. data/profile.json -> app_settings["profile"]
    if OLD_PROFILE_PATH.exists():
        settings_repo.set("profile", OLD_PROFILE_PATH.read_text())
        summary["profile"] = True

    # 3. data/cache/default_provider.json -> app_settings["default_provider"]
    default_provider_path = OLD_CACHE_DIR / "default_provider.json"
    if default_provider_path.exists():
        try:
            provider = json.loads(default_provider_path.read_text())["provider"]
            settings_repo.set("default_provider", provider)
            summary["default_provider"] = True
        except (json.JSONDecodeError, KeyError):
            print(f"warning: could not parse {default_provider_path}, skipping")

    # 4. data/cache/model_capabilities.json -> app_settings["model_capabilities"]
    model_capabilities_path = OLD_CACHE_DIR / "model_capabilities.json"
    if model_capabilities_path.exists():
        settings_repo.set("model_capabilities", model_capabilities_path.read_text())
        summary["model_capabilities"] = True

    # 5. data/games/<id>/research.yaml (+ sibling data/research/<id>/) -> game_research row
    if GAMES_DIR.exists():
        for research_yaml_path in sorted(GAMES_DIR.glob("*/research.yaml")):
            game_id = research_yaml_path.parent.name
            with open(research_yaml_path) as f:
                research_data = yaml.safe_load(f) or {}
            notes = research_data.get("research_notes", "")

            game_research_dir = OLD_RESEARCH_DIR / game_id
            sources_path = game_research_dir / "sources.json"
            raw_dir = game_research_dir / "raw"

            query = ""
            sources: list[str] = []
            if sources_path.exists():
                try:
                    sources_data = json.loads(sources_path.read_text())
                    query = sources_data.get("query", "")
                    sources = sources_data.get("sources", [])
                except json.JSONDecodeError:
                    pass

            raw: list[dict] = []
            if raw_dir.exists():
                for raw_path in sorted(raw_dir.glob("*.txt")):
                    text = raw_path.read_text()
                    # Raw files were written as "URL: <url>\n\n<text>" by
                    # the old Researcher - split that back apart so
                    # sources_json's shape matches what the new code writes.
                    url = ""
                    body = text
                    if text.startswith("URL: "):
                        first_line, _, rest = text.partition("\n\n")
                        url = first_line[len("URL: ") :].strip()
                        body = rest
                    raw.append({"url": url, "text": body})

            sources_json = json.dumps({"query": query, "sources": sources, "raw": raw})
            research_repo.set(game_id, notes, sources_json=sources_json)
            summary["game_research_rows"] += 1

    # 6. Move the db file itself to its new home.
    if OLD_DB_PATH.exists():
        shutil.move(str(OLD_DB_PATH), str(NEW_DB_PATH))
        summary["db_moved"] = True

    # 7. Delete now-obsolete files/dirs.
    for path in (OLD_DB_DIR, OLD_CACHE_DIR, OLD_RESEARCH_DIR, OLD_SESSIONS_DIR):
        if path.exists():
            shutil.rmtree(path)
    if OLD_PROFILE_PATH.exists():
        OLD_PROFILE_PATH.unlink()
    if GAMES_DIR.exists():
        for research_yaml_path in GAMES_DIR.glob("*/research.yaml"):
            research_yaml_path.unlink()

    # 8. Summary.
    print("Migration complete:")
    print(f"  profile.json migrated: {summary['profile']}")
    print(f"  default_provider.json migrated: {summary['default_provider']}")
    print(f"  model_capabilities.json migrated: {summary['model_capabilities']}")
    print(f"  game_research rows written: {summary['game_research_rows']}")
    print(f"  db moved to {NEW_DB_PATH}: {summary['db_moved']}")


if __name__ == "__main__":
    main()
