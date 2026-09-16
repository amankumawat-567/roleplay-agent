import yaml


def write_game(games_dir, game_id: str = "alpha", **overrides) -> None:
    data = {
        "title": "Alpha",
        "model": "llama3.1",
        "starter": "user",
        "persona": "A persona.",
        "user_role": "A role.",
        "script": "A script.",
    }
    data.update(overrides)
    game_dir = games_dir / game_id
    game_dir.mkdir(parents=True, exist_ok=True)
    with open(game_dir / "game.yaml", "w") as f:
        yaml.safe_dump(data, f)
