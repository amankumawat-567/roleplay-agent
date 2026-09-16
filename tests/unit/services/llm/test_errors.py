import httpx
from ollama import ResponseError

from roleplay_agent.services.llm.errors import describe_llm_error


def test_describes_transport_error_as_unreachable():
    exc = httpx.ConnectError("Connection refused")
    message = describe_llm_error(exc)
    assert "running" in message.lower()


def test_describes_response_error_with_ollamas_own_message():
    exc = ResponseError("model 'x' not found", status_code=404)
    assert "model 'x' not found" in describe_llm_error(exc)


def test_falls_back_for_unrelated_exceptions():
    message = describe_llm_error(ValueError("something else"))
    assert message == "Unexpected error talking to the model."
