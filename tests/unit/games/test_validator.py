import pytest

from roleplay_agent.games.validator import GameConfigError, validate_game


def test_validate_game_returns_game_for_valid_data():
    game = validate_game(
        "g1",
        {"title": "T", "model": "llama3.1", "persona": "P", "user_role": "U", "script": "S"},
    )
    assert game.id == "g1"
    assert game.title == "T"


def test_validate_game_raises_clear_error_for_missing_fields():
    with pytest.raises(GameConfigError, match="g1"):
        validate_game("g1", {"title": "T"})
