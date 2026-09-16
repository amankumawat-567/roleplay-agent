import re
import time
from pathlib import Path

import yaml

from roleplay_agent.games.models import Game
from roleplay_agent.games.validator import GameConfigError, validate_game
from roleplay_agent.games.yaml_io import dump_yaml
from roleplay_agent.services.storage.repositories import GameResearchRepository

_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")
VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class GameLoader:
    """Reads persona definitions from data/games/<id>/game.yaml. An
    optional `research_repo` (the `game_research` sqlite table) supplies
    research_notes - written separately by the research pipeline
    (research/researcher.py) so authored persona content and generated
    research notes never share a file."""

    def __init__(self, games_dir: Path, research_repo: GameResearchRepository | None = None):
        self.games_dir = games_dir
        self.research_repo = research_repo

    def _game_dir(self, game_id: str) -> Path:
        return self.games_dir / game_id

    def load(self, game_id: str) -> Game:
        path = self._game_dir(game_id) / "game.yaml"
        if not path.exists():
            raise FileNotFoundError(f"No such game: {game_id}")
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        if self.research_repo is not None:
            row = self.research_repo.get(game_id)
            if row is not None:
                data.setdefault("research_notes", row.notes)

        return validate_game(game_id, data)

    def list_all(self) -> list[Game]:
        if not self.games_dir.exists():
            return []
        games = []
        for path in sorted(self.games_dir.glob("*/game.yaml")):
            try:
                games.append(self.load(path.parent.name))
            except GameConfigError:
                continue  # keep the picker usable even if one game is broken
        return games

    def save_research_notes(
        self, game_id: str, notes: str, sources_json: str = "", fetched_at: float | None = None
    ) -> None:
        if self.research_repo is None:
            raise RuntimeError("GameLoader has no research_repo configured - can't save research notes.")
        self.research_repo.set(game_id, notes, sources_json, fetched_at or time.time())

    def exists(self, game_id: str) -> bool:
        return (self._game_dir(game_id) / "game.yaml").exists()

    def slug_for_title(self, title: str) -> str:
        """Directory-safe id derived from a title, disambiguated with a
        numeric suffix if it collides with an existing game."""
        base = _SLUG_COLLAPSE_RE.sub("-", title.strip().lower()).strip("-") or "game"
        slug = base
        n = 2
        while self.exists(slug):
            slug = f"{base}-{n}"
            n += 1
        return slug

    def save(self, game: Game) -> None:
        game_dir = self._game_dir(game.id)
        game_dir.mkdir(parents=True, exist_ok=True)
        data = game.model_dump(exclude={"id", "research_notes"}, exclude_none=True)
        dump_yaml(data, game_dir / "game.yaml")
