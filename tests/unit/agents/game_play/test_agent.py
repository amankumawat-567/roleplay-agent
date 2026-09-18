import asyncio

import pytest
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool

from roleplay_agent.agents.game_play import agent as agent_module
from roleplay_agent.agents.game_play.agent import RoleplayAgent
from roleplay_agent.games.models import Game
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import EmbeddingRepository, MessageRepository, SessionRepository


@tool
def echo(text: str) -> str:
    """Echoes back the given text - a minimal tool for testing the loop."""
    return f"echo: {text}"


class _ToolCallingFakeLLM:
    """First call requests the echo tool; second call (once the tool
    result is back in history) returns a plain final reply. Deliberately
    ignores whatever bind_tools was actually given, to prove routing is
    gated on the game's own skills list, not on model behavior."""

    def __init__(self):
        self.call_count = 0
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call_1"}])
        return AIMessage(content="final reply")

BASE_GAME = Game(
    id="g1",
    title="Test",
    model="test-model",
    persona="A persona.",
    user_role="A role.",
    script="A script.",
)


class _FakeLLM:
    def __init__(self, async_reply="a reply"):
        self.async_reply = async_reply

    async def ainvoke(self, messages):
        return AIMessage(content=self.async_reply)


class _FakeEmbeddings:
    def __init__(self, vector=None):
        self.vector = vector or [1.0, 0.0]
        self.calls: list[str] = []

    async def aembed_query(self, text):
        self.calls.append(text)
        return self.vector


@pytest.fixture
def repos(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return SessionRepository(db), MessageRepository(db)


@pytest.fixture
def embedding_repo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init_db()
    return EmbeddingRepository(db)


def test_prepare_builds_history_from_memory(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    message_repo.add(session_id, "user", "hey there")

    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m")
    state = {"session_id": session_id, "game": BASE_GAME, "num_ctx": 4096, "history": [], "reply": ""}
    result = asyncio.run(agent._prepare(state))

    history = result["history"]
    assert isinstance(history[0], SystemMessage)
    assert "A persona." in history[0].content
    assert any(getattr(m, "content", None) == "hey there" for m in history)


def test_generate_returns_llm_reply(repos, monkeypatch):
    session_repo, message_repo = repos
    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m")
    calls = []

    def fake_build_llm(provider, model, num_ctx, keep_alive, reasoning=None):
        calls.append((provider, model, num_ctx, keep_alive))
        return _FakeLLM(async_reply="a reply")

    monkeypatch.setattr(agent_module, "build_llm", fake_build_llm)

    state = {
        "session_id": "s1",
        "game": BASE_GAME,
        "num_ctx": 4096,
        "history": [SystemMessage(content="sys")],
        "reply": "",
    }
    result = asyncio.run(agent._generate(state))
    assert result["reply"] == "a reply"
    assert calls == [("ollama", "test-model", 4096, "30m")]  # BASE_GAME.provider defaults to "ollama"


def test_prepare_skips_recall_when_memory_recall_disabled(repos, embedding_repo):
    # BASE_GAME.memory_recall defaults to False - recall must stay a no-op
    # (no embedding call at all) even though embeddings/embedding_repo are wired.
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    embeddings = _FakeEmbeddings()

    agent = RoleplayAgent(
        session_repo, message_repo, keep_last=20, keep_alive="30m", embedding_repo=embedding_repo, embeddings=embeddings
    )
    state = {
        "session_id": session_id,
        "game": BASE_GAME,
        "num_ctx": 4096,
        "message": "what's up",
        "history": [],
        "reply": "",
    }
    asyncio.run(agent._prepare(state))

    assert embeddings.calls == []


def test_generate_binds_tools_scoped_to_game_skills(repos, monkeypatch):
    session_repo, message_repo = repos
    fake_llm = _ToolCallingFakeLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)

    game = BASE_GAME.model_copy(update={"skills": ["echo"]})
    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m", skill_tools={"echo": echo})
    state = {
        "session_id": "s1",
        "game": game,
        "num_ctx": 4096,
        "history": [SystemMessage(content="sys")],
        "reply": "",
    }

    asyncio.run(agent._generate(state))

    assert fake_llm.bound_tools == [echo]


def test_generate_does_not_bind_tools_when_game_has_no_skills(repos, monkeypatch):
    # BASE_GAME.skills defaults to [] - even though the agent has "echo"
    # available globally, this game never asked for it.
    session_repo, message_repo = repos
    fake_llm = _ToolCallingFakeLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)

    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m", skill_tools={"echo": echo})
    state = {
        "session_id": "s1",
        "game": BASE_GAME,
        "num_ctx": 4096,
        "history": [SystemMessage(content="sys")],
        "reply": "",
    }

    asyncio.run(agent._generate(state))

    assert fake_llm.bound_tools is None


def test_full_graph_loops_through_a_tool_call_then_ends(repos, monkeypatch):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    fake_llm = _ToolCallingFakeLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)

    game = BASE_GAME.model_copy(update={"skills": ["echo"]})
    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m", skill_tools={"echo": echo})
    initial_state = {
        "session_id": session_id,
        "game": game,
        "num_ctx": 4096,
        "message": "say hi",
        "history": [],
        "reply": "",
    }

    result = asyncio.run(agent.graph.ainvoke(initial_state))

    assert fake_llm.call_count == 2  # the tool-deciding round, then the final round
    final_messages = result["history"]
    assert any(getattr(m, "content", None) == "echo: hi" for m in final_messages)  # the tool really ran
    assert final_messages[-1].content == "final reply"


def test_full_graph_never_runs_a_tool_for_a_game_without_skills(repos, monkeypatch):
    # The fake always requests the echo tool on its first call, regardless
    # of what was bound - proves routing itself (not just bind_tools)
    # refuses to run a tool this game's skills list didn't authorize.
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    fake_llm = _ToolCallingFakeLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)

    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m", skill_tools={"echo": echo})
    initial_state = {
        "session_id": session_id,
        "game": BASE_GAME,  # skills=[]
        "num_ctx": 4096,
        "message": "say hi",
        "history": [],
        "reply": "",
    }

    result = asyncio.run(agent.graph.ainvoke(initial_state))

    assert fake_llm.call_count == 1  # never looped back for a second round
    assert not any(getattr(m, "content", None) == "echo: hi" for m in result["history"])  # tool never ran


class _AlwaysToolCallingFakeLLM:
    """Never gives a plain final reply - every call re-requests the tool.
    Stands in for a model stuck re-issuing tool calls instead of ever
    answering, to prove the graph can't loop the generate<->tools edge
    forever."""

    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        call = {"name": "echo", "args": {"text": "hi"}, "id": f"call_{self.call_count}"}
        return AIMessage(content="", tool_calls=[call])


def test_full_graph_stops_looping_a_model_that_keeps_calling_tools(repos, monkeypatch):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    fake_llm = _AlwaysToolCallingFakeLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)

    game = BASE_GAME.model_copy(update={"skills": ["echo"]})
    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m", skill_tools={"echo": echo})
    initial_state = {
        "session_id": session_id,
        "game": game,
        "num_ctx": 4096,
        "message": "say hi",
        "history": [],
        "reply": "",
    }

    result = asyncio.run(agent.graph.ainvoke(initial_state))

    # One generate call per allowed tool round, plus the final call whose
    # tool request gets refused rather than run - never unbounded.
    assert fake_llm.call_count == agent_module.MAX_TOOL_ROUNDS + 1
    tool_results = [m for m in result["history"] if type(m).__name__ == "ToolMessage"]
    assert len(tool_results) == agent_module.MAX_TOOL_ROUNDS


def test_prepare_includes_recalled_memories_when_enabled(repos, embedding_repo):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    embedding_repo.add("g1", session_id, "Sam mentioned moving to Denver.", [1.0, 0.0])

    game = BASE_GAME.model_copy(update={"memory_recall": True})
    embeddings = _FakeEmbeddings(vector=[1.0, 0.0])
    agent = RoleplayAgent(
        session_repo, message_repo, keep_last=20, keep_alive="30m", embedding_repo=embedding_repo, embeddings=embeddings
    )
    state = {
        "session_id": session_id,
        "game": game,
        "num_ctx": 4096,
        "message": "how's the move going",
        "history": [],
        "reply": "",
    }
    result = asyncio.run(agent._prepare(state))

    assert embeddings.calls == ["how's the move going"]
    system_prompt = result["history"][0].content
    assert "Sam mentioned moving to Denver." in system_prompt


def test_prepare_includes_followup_reason_when_set(repos):
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")

    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m")
    state = {
        "session_id": session_id,
        "game": BASE_GAME,
        "num_ctx": 4096,
        "message": None,
        "followup_reason": "promised to check how the exam went",
        "history": [],
        "reply": "",
    }
    result = asyncio.run(agent._prepare(state))

    assert "promised to check how the exam went" in result["history"][0].content


def test_prepare_skips_recall_when_no_incoming_message(repos, embedding_repo):
    # An AI-starter turn has no user message yet - nothing to embed against.
    session_repo, message_repo = repos
    session_id = session_repo.create("g1", "Title")
    game = BASE_GAME.model_copy(update={"memory_recall": True})
    embeddings = _FakeEmbeddings()

    agent = RoleplayAgent(
        session_repo, message_repo, keep_last=20, keep_alive="30m", embedding_repo=embedding_repo, embeddings=embeddings
    )
    state = {
        "session_id": session_id,
        "game": game,
        "num_ctx": 4096,
        "message": None,
        "history": [],
        "reply": "",
    }
    asyncio.run(agent._prepare(state))

    assert embeddings.calls == []
