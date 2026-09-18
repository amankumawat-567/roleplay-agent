import pytest

from roleplay_agent.services.llm import anthropic as anthropic_module
from roleplay_agent.services.llm import ollama as ollama_module
from roleplay_agent.services.llm import openai as openai_module
from roleplay_agent.services.llm.providers import ProviderConfigError
from roleplay_agent.services.llm.registry import build_llm


def test_build_llm_dispatches_to_ollama_with_configured_base_url(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ollama_module,
        "build_llm",
        lambda model, num_ctx, keep_alive, base_url=None, reasoning=None: (
            calls.append((model, num_ctx, keep_alive, base_url, reasoning)) or "ollama-llm"
        ),
    )

    result = build_llm("ollama", "llama3.1", 8192, "30m")

    assert result == "ollama-llm"
    assert calls == [("llama3.1", 8192, "30m", "http://127.0.0.1:11434", None)]


def test_build_llm_forwards_reasoning_to_ollama(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ollama_module,
        "build_llm",
        lambda model, num_ctx, keep_alive, base_url=None, reasoning=None: calls.append(reasoning) or "ollama-llm",
    )

    build_llm("ollama", "llama3.1", 8192, "30m", reasoning=False)

    assert calls == [False]


def test_build_llm_dispatches_to_openai(monkeypatch):
    monkeypatch.setattr(openai_module, "build_llm", lambda model, config: f"openai:{model}:{config.kind}")

    result = build_llm("openai", "gpt-4o-mini", 8192, "30m")

    assert result == "openai:gpt-4o-mini:openai"


def test_build_llm_dispatches_to_anthropic(monkeypatch):
    monkeypatch.setattr(anthropic_module, "build_llm", lambda model, config: f"anthropic:{model}:{config.kind}")

    result = build_llm("anthropic", "claude-3-5-sonnet-20241022", 8192, "30m")

    assert result == "anthropic:claude-3-5-sonnet-20241022:anthropic"


def test_build_llm_unknown_provider_raises_clear_error():
    with pytest.raises(ProviderConfigError):
        build_llm("does-not-exist", "some-model", 8192, "30m")
