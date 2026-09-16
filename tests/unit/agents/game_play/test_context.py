import base64

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from roleplay_agent.agents.game_play.context import to_audio_message, to_lc_messages
from roleplay_agent.services.storage.models import Message


def test_to_lc_messages_maps_roles():
    messages = to_lc_messages(
        "sys prompt",
        [Message(role="user", content="hi"), Message(role="assistant", content="hello")],
    )
    assert isinstance(messages[0], SystemMessage) and messages[0].content == "sys prompt"
    assert isinstance(messages[1], HumanMessage) and messages[1].content == "hi"
    assert isinstance(messages[2], AIMessage) and messages[2].content == "hello"


def test_to_audio_message_encodes_wav_bytes_as_data_url():
    message = to_audio_message(b"fake-wav-bytes")

    assert isinstance(message, HumanMessage)
    [block] = message.content
    assert block["type"] == "image_url"
    prefix = "data:audio/wav;base64,"
    assert block["image_url"].startswith(prefix)
    encoded = block["image_url"][len(prefix) :]
    assert base64.b64decode(encoded) == b"fake-wav-bytes"
