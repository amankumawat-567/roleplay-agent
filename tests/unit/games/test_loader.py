import pytest
import yaml

from roleplay_agent.games.loader import GameLoader
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import GameResearchRepository


@pytest.fixture
def games_dir(tmp_path):
    d = tmp_path / "games"
    d.mkdir()
    return d


def _write_game(games_dir, game_id, **overrides):
    data = {
        "title": f"{game_id} title",
        "model": "llama3.1",
        "starter": "ai",
        "persona": "A persona.",
        "user_role": "A role.",
        "script": "A script.",
    }
    data.update(overrides)
    d = games_dir / game_id
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "game.yaml", "w") as f:
        yaml.safe_dump(data, f)


def test_list_all_reads_every_game(games_dir):
    _write_game(games_dir, "alpha", tags=["casual", "drama"])
    _write_game(games_dir, "beta")

    games = GameLoader(games_dir).list_all()
    assert [g.id for g in games] == ["alpha", "beta"]  # sorted by directory name


def test_list_all_defaults_missing_tags_to_empty_list(games_dir):
    _write_game(games_dir, "beta")
    beta = next(g for g in GameLoader(games_dir).list_all() if g.id == "beta")
    assert beta.tags == []


def test_load_returns_validated_game(games_dir):
    _write_game(games_dir, "alpha", tags=["casual"])
    game = GameLoader(games_dir).load("alpha")
    assert game.title == "alpha title"
    assert game.tags == ["casual"]
    assert game.starter == "ai"


def test_load_missing_raises_file_not_found(games_dir):
    with pytest.raises(FileNotFoundError):
        GameLoader(games_dir).load("does-not-exist")


def test_load_merges_research_notes_from_separate_file(games_dir, tmp_path):
    _write_game(games_dir, "alpha")
    db = Database(tmp_path / "test.db")
    db.init_db()
    research_repo = GameResearchRepository(db)
    loader = GameLoader(games_dir, research_repo)
    loader.save_research_notes("alpha", "Uses casual phrasing.")

    game = loader.load("alpha")
    assert game.research_notes == "Uses casual phrasing."


def test_list_all_skips_invalid_game_but_keeps_others(games_dir):
    _write_game(games_dir, "good")
    (games_dir / "bad").mkdir()
    (games_dir / "bad" / "game.yaml").write_text("title: Bad\n")  # missing required fields

    games = GameLoader(games_dir).list_all()
    assert [g.id for g in games] == ["good"]


def test_load_invalid_game_raises_clear_error(games_dir):
    (games_dir / "bad").mkdir()
    (games_dir / "bad" / "game.yaml").write_text("title: Bad\n")

    from roleplay_agent.games.validator import GameConfigError

    with pytest.raises(GameConfigError):
        GameLoader(games_dir).load("bad")


def test_exists_true_for_saved_game(games_dir):
    _write_game(games_dir, "alpha")
    assert GameLoader(games_dir).exists("alpha") is True


def test_exists_false_for_missing_game(games_dir):
    assert GameLoader(games_dir).exists("nope") is False


def test_slug_for_title_slugifies(games_dir):
    loader = GameLoader(games_dir)
    assert loader.slug_for_title("My Cool Game!") == "my-cool-game"


def test_slug_for_title_disambiguates_collisions(games_dir):
    _write_game(games_dir, "my-game")
    loader = GameLoader(games_dir)
    assert loader.slug_for_title("My Game") == "my-game-2"


def test_save_writes_loadable_game(games_dir):
    from roleplay_agent.games.models import Game

    game = Game(
        id="alpha",
        title="Alpha",
        tags=["casual"],
        provider="openai",
        model="llama3.1",
        starter="ai",
        persona="A persona.",
        user_role="A role.",
        script="A script.",
    )
    loader = GameLoader(games_dir)
    loader.save(game)

    reloaded = loader.load("alpha")
    assert reloaded.title == "Alpha"
    assert reloaded.tags == ["casual"]
    assert reloaded.starter == "ai"
    assert reloaded.provider == "openai"


def test_load_defaults_provider_to_ollama_when_absent(games_dir):
    _write_game(games_dir, "alpha")
    assert GameLoader(games_dir).load("alpha").provider == "ollama"


def test_save_omits_research_notes_from_game_yaml(games_dir):
    from roleplay_agent.games.models import Game

    game = Game(
        id="alpha",
        title="Alpha",
        model="llama3.1",
        persona="A persona.",
        user_role="A role.",
        script="A script.",
        research_notes="Should not be persisted here.",
    )
    GameLoader(games_dir).save(game)

    raw = yaml.safe_load((games_dir / "alpha" / "game.yaml").read_text())
    assert "research_notes" not in raw
