from pydantic import ValidationError

from roleplay_agent.games.models import Game


class GameConfigError(ValueError):
    pass


def validate_game(game_id: str, data: dict) -> Game:
    try:
        return Game(id=game_id, **data)
    except ValidationError as exc:
        raise GameConfigError(f"Invalid game config '{game_id}': {exc}") from exc
