import asyncio

from langchain_core.embeddings import Embeddings
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from roleplay_agent.agents.game_play.context import ChatState, to_lc_messages
from roleplay_agent.agents.game_play.prompts import build_system_prompt
from roleplay_agent.components.memory.context import get_context
from roleplay_agent.services.llm.registry import build_llm
from roleplay_agent.services.storage.repositories import EmbeddingRepository, MessageRepository, SessionRepository

RECALL_TOP_K = 3  # matches the running summary's "4-6 bullets" scale

# Ceiling on tool round-trips within a single turn - a well-behaved turn
# calls a tool once or twice and then answers in plain text, so this never
# bites in practice; it exists purely to stop a model that keeps re-issuing
# tool calls (e.g. schedule_followup) from looping the generate<->tools
# edge indefinitely instead of ever producing a reply for the user.
MAX_TOOL_ROUNDS = 3


class RoleplayAgent:
    """The per-turn conversation graph: prepare (build the prompt from
    stored history + summary) -> generate (stream the model's reply) ->
    generate loops through a tool call/ToolNode round-trip for any game
    whose `skills` list gave the model something to call, otherwise ends
    immediately - identical to the pre-skills graph shape for those games.
    Summarization is handled separately (see memory.manager) - it never
    runs as part of this graph, so it can never add latency to a turn."""

    def __init__(
        self,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        keep_last: int,
        keep_alive: str,
        embedding_repo: EmbeddingRepository | None = None,
        embeddings: Embeddings | None = None,
        skill_tools: dict[str, BaseTool] | None = None,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.keep_last = keep_last
        self.keep_alive = keep_alive
        self.embedding_repo = embedding_repo
        self.embeddings = embeddings
        self.skill_tools = skill_tools or {}
        self.graph = self._build_graph()

    async def _recall_memories(self, game, message: str | None) -> list[str]:
        # Off unless a game opts in (Game.memory_recall) - zero added
        # latency/cost for every game that doesn't, which is the default.
        if not game.memory_recall or not message or self.embedding_repo is None or self.embeddings is None:
            return []
        query_vector = await self.embeddings.aembed_query(message)
        chunks = await asyncio.to_thread(self.embedding_repo.search, game.id, query_vector, RECALL_TOP_K)
        return [c.text for c in chunks]

    async def _prepare(self, state: ChatState) -> dict:
        # Pure read (see memory.context.get_context), but still off the
        # event loop since it's blocking sqlite I/O.
        summary, recent = await asyncio.to_thread(
            get_context, self.session_repo, self.message_repo, state["session_id"], self.keep_last
        )
        game = state["game"]
        recalled_memories = await self._recall_memories(game, state.get("message"))
        system_prompt = build_system_prompt(game, summary, recalled_memories, state.get("followup_reason"))
        return {"history": to_lc_messages(system_prompt, recent)}

    async def _generate(self, state: ChatState) -> dict:
        game = state["game"]
        llm = build_llm(game.provider, game.model, state["num_ctx"], self.keep_alive)
        tools = [self.skill_tools[sid] for sid in game.skills if sid in self.skill_tools]
        if tools:
            llm = llm.bind_tools(tools)
        response = await llm.ainvoke(state["history"])
        # Appended (via ChatState.history's add_messages reducer), not a
        # replacement - a looping turn needs every prior round still there
        # the next time _generate runs.
        return {"history": [response], "reply": response.content}

    def _route_after_generate(self, state: ChatState) -> str:
        last = state["history"][-1]
        tool_calls = getattr(last, "tool_calls", None)
        if not tool_calls:
            return END
        # Defense in depth: only ever run a tool this specific game actually
        # authorized (via game.skills), even though _generate only ever
        # binds that same subset to the model - a well-behaved provider
        # can't emit a call for a tool it wasn't given, but ToolNode itself
        # is shared/built from *every* registered skill, so this is what
        # actually stops a misbehaving model from reaching a tool outside
        # this game's own skills list.
        authorized = set(state["game"].skills)
        if not all(tc["name"] in authorized for tc in tool_calls):
            return END
        # Each completed tool round leaves its result(s) in history as
        # ToolMessage(s) - counting those (rather than a separate counter
        # field) needs no extra state and naturally resets per turn, since
        # history is rebuilt from scratch by `prepare` every invocation.
        rounds_so_far = sum(1 for m in state["history"] if isinstance(m, ToolMessage))
        if rounds_so_far >= MAX_TOOL_ROUNDS:
            return END
        return "tools"

    def _build_graph(self):
        graph = StateGraph(ChatState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("generate", self._generate)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "generate")

        if self.skill_tools:
            # Built once from every registered skill; which of them the
            # model can actually call is scoped per-game in _generate via
            # bind_tools, so ToolNode only ever runs a tool the model was
            # actually offered.
            graph.add_node("tools", ToolNode(list(self.skill_tools.values()), messages_key="history"))
            graph.add_conditional_edges("generate", self._route_after_generate, {"tools": "tools", END: END})
            graph.add_edge("tools", "generate")
        else:
            graph.add_edge("generate", END)

        return graph.compile()
