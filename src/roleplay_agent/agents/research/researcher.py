import json
import time

from roleplay_agent.agents.research.browser import fetch_snippets
from roleplay_agent.agents.research.summarizer import summarize_style
from roleplay_agent.games.loader import GameLoader
from roleplay_agent.services.llm.capabilities import resolve_game_model
from roleplay_agent.services.storage.repositories import GameResearchRepository, SettingsRepository


class Researcher:
    """Runs the one-shot web research step for a game and persists both the
    raw artifacts and the distilled notes the agent actually reads at
    runtime into the `game_research` sqlite table (via
    GameLoader.save_research_notes) - see GameResearchRepository."""

    def __init__(
        self,
        loader: GameLoader,
        research_repo: GameResearchRepository,
        user_agent: str,
        max_results: int,
        keep_alive: str,
        default_num_ctx: int,
        settings_repo: SettingsRepository,
        enable_thinking: bool | None = None,
    ):
        self.loader = loader
        self.research_repo = research_repo
        self.user_agent = user_agent
        self.max_results = max_results
        self.keep_alive = keep_alive
        self.default_num_ctx = default_num_ctx
        self.settings_repo = settings_repo
        self.enable_thinking = enable_thinking

    def research(self, game_id: str) -> str:
        game = self.loader.load(game_id)
        query = game.research_query or f"{game.title} casual dialogue examples"
        snippets = fetch_snippets(query, self.user_agent, self.max_results)

        sources_json = json.dumps(
            {
                "query": query,
                "sources": [s["url"] for s in snippets],
                "raw": [{"url": s["url"], "text": s["text"]} for s in snippets],
            }
        )

        # A `model: default` persona (see resolve_game_model) resolves here
        # too - the research pipeline reloads the game itself rather than
        # reusing whatever the route's own get_game_or_404 dependency saw.
        provider, model = resolve_game_model(game.provider, game.model, self.settings_repo)

        notes = summarize_style(
            game.persona,
            snippets,
            provider,
            model,
            game.num_ctx or self.default_num_ctx,
            self.keep_alive,
            enable_thinking=self.enable_thinking,
        )

        self.loader.save_research_notes(game_id, notes, sources_json=sources_json, fetched_at=time.time())
        return notes
