import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from roleplay_agent.config.settings import AppConfig, Settings
from roleplay_agent.services.storage.database import Database
from roleplay_agent.services.storage.repositories import FollowupRepository
from roleplay_agent.skills.schedule_followup import build_schedule_followup_tool


class _State(TypedDict):
    session_id: str
    history: Annotated[list, add_messages]


def _invoke(tool, session_id: str, minutes, reason: str):
    # schedule_followup's session_id is InjectedState, not model-supplied -
    # that's only resolved by a real compiled-graph run (like
    # agent.agent.RoleplayAgent's own graph), not a bare ToolNode.invoke().
    graph = StateGraph(_State)
    graph.add_node("tools", ToolNode([tool], messages_key="history"))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()

    tool_call = {
        "name": "schedule_followup",
        "args": {"minutes": minutes, "reason": reason},
        "id": "call_1",
        "type": "tool_call",
    }
    state = {"session_id": session_id, "history": [AIMessage(content="", tool_calls=[tool_call])]}
    result = compiled.invoke(state)
    return result["history"][-1]


def _settings(tmp_path) -> Settings:
    settings = Settings(data_dir=tmp_path / "data")
    Database(settings.db_path).init_db()
    return settings


def _app_config() -> AppConfig:
    return AppConfig(
        embedding_model="nomic-embed-text",
        stt_model_repo="openai/whisper-tiny",
        tts_backend="chatterbox",
        tts_chatterbox_model_repo="x",
    )


def test_schedule_followup_writes_a_pending_row(tmp_path):
    settings = _settings(tmp_path)
    tool = build_schedule_followup_tool(settings, _app_config())
    before = time.time()

    message = _invoke(tool, "s1", 10, "check if the interview went well")

    followup = FollowupRepository(Database(settings.db_path)).next_for_session("s1")
    assert followup is not None
    assert followup.reason == "check if the interview went well"
    assert 9 * 60 <= followup.fire_at - before <= 11 * 60
    assert "10 minute" in message.content


def test_schedule_followup_clamps_minutes_to_a_day():
    from roleplay_agent.skills.schedule_followup import _MAX_MINUTES, _MIN_MINUTES

    assert _MAX_MINUTES == 24 * 60
    assert _MIN_MINUTES == 1


def test_schedule_followup_clamps_excessive_minutes(tmp_path):
    settings = _settings(tmp_path)
    tool = build_schedule_followup_tool(settings, _app_config())
    before = time.time()

    _invoke(tool, "s1", 999999, "way too far out")

    followup = FollowupRepository(Database(settings.db_path)).next_for_session("s1")
    assert followup.fire_at - before <= 24 * 60 * 60 + 5


def test_schedule_followup_session_id_is_injected_not_model_supplied(tmp_path):
    settings = _settings(tmp_path)
    tool = build_schedule_followup_tool(settings, _app_config())
    assert "session_id" not in tool.args  # excluded from the model-visible schema

    _invoke(tool, "the-real-session", 5, "reason")

    repo = FollowupRepository(Database(settings.db_path))
    assert repo.next_for_session("the-real-session") is not None
