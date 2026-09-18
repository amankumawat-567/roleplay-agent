import asyncio

import pytest
from langchain_core.messages import AIMessage

from roleplay_agent.agents.game_play import agent as agent_module
from roleplay_agent.agents.game_play.agent import RoleplayAgent
from roleplay_agent.agents.game_play.followups import deliver_due_followups
from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.games.loader import GameLoader
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import FollowupRepository, MessageRepository, SessionRepository
from roleplay_agent.skills.schedule_followup import build_schedule_followup_tool
from tests.helpers import write_game


class _FakeLLM:
    def __init__(self, reply="checking in on you"):
        self.reply = reply

    async def ainvoke(self, messages):
        return AIMessage(content=self.reply)


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = Database(tmp_path / "test.db")
    db.init_db()
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    followup_repo = FollowupRepository(db)
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    game_loader = GameLoader(games_dir)

    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: _FakeLLM())
    agent = RoleplayAgent(session_repo, message_repo, keep_last=20, keep_alive="30m")

    return {
        "session_repo": session_repo,
        "message_repo": message_repo,
        "followup_repo": followup_repo,
        "game_loader": game_loader,
        "games_dir": games_dir,
        "agent": agent,
    }


async def _deliver(env, now=None):
    return await deliver_due_followups(
        env["followup_repo"],
        env["session_repo"],
        env["message_repo"],
        env["game_loader"],
        env["agent"],
        default_num_ctx=4096,
        now=now,
    )


def test_delivers_a_due_followup_as_an_assistant_message(env):
    write_game(env["games_dir"], "alpha")
    session_id = env["session_repo"].create("alpha", "Alpha")
    env["followup_repo"].schedule(session_id, fire_at=100.0, reason="ask how the exam went")

    delivered = asyncio.run(_deliver(env, now=200.0))

    assert delivered == 1
    messages = env["message_repo"].list_for_session(session_id)
    assert [m.role for m in messages] == ["assistant"]
    assert messages[0].content == "checking in on you"


def test_skips_and_removes_a_followup_not_yet_due(env):
    write_game(env["games_dir"], "alpha")
    session_id = env["session_repo"].create("alpha", "Alpha")
    env["followup_repo"].schedule(session_id, fire_at=1000.0, reason="not yet")

    delivered = asyncio.run(_deliver(env, now=100.0))

    assert delivered == 0
    assert env["message_repo"].list_for_session(session_id) == []
    assert env["followup_repo"].next_for_session(session_id) is not None  # still pending


def test_removes_the_row_once_delivered(env):
    write_game(env["games_dir"], "alpha")
    session_id = env["session_repo"].create("alpha", "Alpha")
    env["followup_repo"].schedule(session_id, fire_at=100.0, reason="ask how the exam went")

    asyncio.run(_deliver(env, now=200.0))

    assert env["followup_repo"].next_for_session(session_id) is None


def test_drops_a_followup_for_a_session_that_no_longer_exists(env):
    env["followup_repo"].schedule("ghost-session", fire_at=100.0, reason="orphaned")

    delivered = asyncio.run(_deliver(env, now=200.0))

    assert delivered == 0
    assert env["followup_repo"].next_for_session("ghost-session") is None  # dropped, not retried forever


def test_drops_a_followup_whose_game_no_longer_exists(env):
    # The session exists but its game.yaml has since been deleted -
    # game_loader.load raises FileNotFoundError, caught and dropped rather
    # than retried on every future poll.
    write_game(env["games_dir"], "alpha")
    session_id = env["session_repo"].create("alpha", "Alpha")
    (env["games_dir"] / "alpha" / "game.yaml").unlink()
    env["followup_repo"].schedule(session_id, fire_at=100.0, reason="game got deleted")

    delivered = asyncio.run(_deliver(env, now=200.0))

    assert delivered == 0
    assert env["followup_repo"].next_for_session(session_id) is None
    assert env["message_repo"].list_for_session(session_id) == []


class _ScheduleThenReplyLLM:
    """First call asks to schedule a follow-up; once the tool result is
    back in history, the second call gives a plain final reply - mirrors
    _ToolCallingFakeLLM in test_agent.py."""

    def __init__(self):
        self.call_count = 0
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "schedule_followup",
                        "args": {"minutes": 10, "reason": "ask how the exam went"},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="alright, talk soon")


def test_scheduling_via_the_real_graph_then_delivering_it_end_to_end(env, tmp_path, monkeypatch):
    # Proves the two halves actually fit together: the schedule_followup
    # tool (bound only because this game's skills list authorizes it)
    # writes a row scoped to the live session_id via InjectedState, and
    # the delivery loop later picks that exact row up and replies in the
    # same session.
    write_game(env["games_dir"], "alpha", skills=["schedule_followup"])
    session_id = env["session_repo"].create("alpha", "Alpha")
    env["message_repo"].add(session_id, "user", "let me know how it goes")

    settings = Settings(data_dir=tmp_path / "settings-data")
    Database(settings.db_path).init_db()
    app_config = AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
    )
    tool = build_schedule_followup_tool(settings, app_config)
    followup_repo = FollowupRepository(Database(settings.db_path))

    fake_llm = _ScheduleThenReplyLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)
    scheduling_agent = RoleplayAgent(
        env["session_repo"],
        env["message_repo"],
        keep_last=20,
        keep_alive="30m",
        skill_tools={"schedule_followup": tool},
    )
    game = env["game_loader"].load("alpha")
    initial_state = {
        "session_id": session_id,
        "game": game,
        "num_ctx": 4096,
        "message": "let me know how it goes",
        "followup_reason": None,
        "history": [],
        "reply": "",
    }

    asyncio.run(scheduling_agent.graph.ainvoke(initial_state))

    scheduled = followup_repo.next_for_session(session_id)
    assert scheduled is not None
    assert scheduled.reason == "ask how the exam went"

    # Reuses scheduling_agent (and its fake_llm) for delivery too, rather
    # than env["agent"] - build_llm is monkeypatched at module level for
    # the whole test, so a second agent would just observe the same fake.
    delivered = asyncio.run(
        deliver_due_followups(
            followup_repo,
            env["session_repo"],
            env["message_repo"],
            env["game_loader"],
            scheduling_agent,
            default_num_ctx=4096,
            now=scheduled.fire_at + 1,
        )
    )

    assert delivered == 1
    assert followup_repo.next_for_session(session_id) is None
    assert fake_llm.call_count == 3  # 2 for scheduling (tool call + reply), 1 more for delivery
    messages = env["message_repo"].list_for_session(session_id)
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "alright, talk soon"


class _DeliverThenScheduleAgainLLM:
    """Stands in for a check-back turn's model: before giving the actual
    check-back reply, it schedules a *second* check-back - proving a
    delivered follow-up isn't special-cased out of tool access and can
    chain straight into the next one (the "several timed questions in a
    row" use case) without the user sending anything in between."""

    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "schedule_followup",
                        "args": {"minutes": 5, "reason": "second question"},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="here's the answer, now try this one")


def test_a_delivered_followup_can_schedule_another_one(env, tmp_path, monkeypatch):
    write_game(env["games_dir"], "alpha", skills=["schedule_followup"])
    session_id = env["session_repo"].create("alpha", "Alpha")

    settings = Settings(data_dir=tmp_path / "settings-data")
    Database(settings.db_path).init_db()
    app_config = AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
    )
    tool = build_schedule_followup_tool(settings, app_config)
    # Same db the tool itself writes to (see build_schedule_followup_tool) -
    # not env["followup_repo"], which points at a different sqlite file.
    followup_repo = FollowupRepository(Database(settings.db_path))
    followup_repo.schedule(session_id, fire_at=100.0, reason="first question")

    fake_llm = _DeliverThenScheduleAgainLLM()
    monkeypatch.setattr(agent_module, "build_llm", lambda *a, **k: fake_llm)
    agent = RoleplayAgent(
        env["session_repo"],
        env["message_repo"],
        keep_last=20,
        keep_alive="30m",
        skill_tools={"schedule_followup": tool},
    )

    delivered = asyncio.run(
        deliver_due_followups(
            followup_repo,
            env["session_repo"],
            env["message_repo"],
            env["game_loader"],
            agent,
            default_num_ctx=4096,
            now=200.0,
        )
    )

    assert delivered == 1
    messages = env["message_repo"].list_for_session(session_id)
    assert messages[-1].content == "here's the answer, now try this one"
    assert messages[-1].kind == "followup"

    chained = followup_repo.next_for_session(session_id)
    assert chained is not None
    assert chained.reason == "second question"


def test_delivers_multiple_due_followups_across_sessions(env):
    write_game(env["games_dir"], "alpha")
    s1 = env["session_repo"].create("alpha", "Alpha")
    s2 = env["session_repo"].create("alpha", "Alpha")
    env["followup_repo"].schedule(s1, fire_at=100.0, reason="one")
    env["followup_repo"].schedule(s2, fire_at=100.0, reason="two")

    delivered = asyncio.run(_deliver(env, now=200.0))

    assert delivered == 2
    assert len(env["message_repo"].list_for_session(s1)) == 1
    assert len(env["message_repo"].list_for_session(s2)) == 1
