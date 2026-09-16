import pytest


def _clear_caches():
    from roleplay_agent.api import dependencies as deps
    from roleplay_agent.config.settings import get_settings

    get_settings.cache_clear()
    for fn in (
        deps.get_database,
        deps.get_session_repo,
        deps.get_message_repo,
        deps.get_embedding_repo,
        deps.get_embeddings,
        deps.get_followup_repo,
        deps.get_skill_tools,
        deps.get_game_loader,
        deps.get_researcher,
        deps.get_agent,
        deps.get_tts_pool,
        deps.get_settings_repo,
        deps.get_game_research_repo,
    ):
        fn.cache_clear()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """Points the app's cached singletons (settings, repos, game loader,
    agent) at an isolated tmp_path data dir for the duration of one test.
    Yields the tmp data_dir. Necessary because api.dependencies wires
    everything through lru_cache'd factories for production use, which
    would otherwise leak state across tests."""
    from roleplay_agent.api import dependencies as deps

    data_dir = tmp_path / "data"
    (data_dir / "games").mkdir(parents=True)
    monkeypatch.setenv("ROLEPLAY_DATA_DIR", str(data_dir))

    _clear_caches()
    deps.get_database().init_db()

    yield data_dir

    _clear_caches()


@pytest.fixture
def client(app_env):
    from fastapi.testclient import TestClient

    from roleplay_agent.main import app

    return TestClient(app)
