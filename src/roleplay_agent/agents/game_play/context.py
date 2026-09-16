import base64
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages

from roleplay_agent.games.models import Game
from roleplay_agent.services.storage.models import Message


class ChatState(TypedDict):
    session_id: str
    game: Game
    num_ctx: int
    message: str | None  # the current turn's raw user text, if any - used for memory recall
    followup_reason: str | None  # set only for a B2 scheduled check-back turn (see agent.followups)
    # add_messages appends/merges rather than overwriting - needed so the
    # skills tool-calling loop (generate -> ToolNode -> generate) accumulates
    # history across rounds instead of each round clobbering the last.
    history: Annotated[list[BaseMessage], add_messages]
    reply: str


def to_lc_messages(system_prompt: str, recent: list[Message]) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    for m in recent:
        cls = HumanMessage if m.role == "user" else AIMessage
        messages.append(cls(content=m.content))
    return messages


def to_audio_message(audio: bytes) -> HumanMessage:
    """The current turn's raw mic audio (WAV bytes), as a message the model
    actually listens to rather than reads - see docs/ARCHITECTURE.md's
    "Voice mode": Ollama's Gemma 4 audio support (v0.33.3+) takes audio
    through the *existing* `images`/`image_url` field, not a dedicated one,
    the same way `langchain_ollama.ChatOllama` forwards a `HumanMessage`
    content block's `image_url` today. Verified live against this project's
    real pulled model before relying on it here."""
    encoded = base64.b64encode(audio).decode()
    return HumanMessage(content=[{"type": "image_url", "image_url": f"data:audio/wav;base64,{encoded}"}])
