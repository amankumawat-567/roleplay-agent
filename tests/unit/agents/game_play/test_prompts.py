from roleplay_agent.agents.game_play.prompts import build_system_prompt, build_voice_system_prompt
from roleplay_agent.games.models import Game

BASE = dict(
    id="g1",
    title="Test",
    model="test-model",
    persona="I am Sam, warm and sarcastic.",
    user_role="The user is Sam's old friend.",
    script="A coffee shop catch-up.",
)


def _game(**overrides) -> Game:
    return Game(**{**BASE, **overrides})


def test_includes_persona_user_role_and_script():
    prompt = build_system_prompt(_game(), summary="")
    assert "I am Sam, warm and sarcastic." in prompt
    assert "The user is Sam's old friend." in prompt
    assert "A coffee shop catch-up." in prompt


def test_omits_research_notes_and_summary_when_absent():
    prompt = build_system_prompt(_game(), summary="")
    assert "Tone/style reference notes" not in prompt
    assert "Summary of the story so far" not in prompt


def test_includes_research_notes_when_present():
    prompt = build_system_prompt(_game(research_notes="Uses short casual sentences."), summary="")
    assert "Tone/style reference notes" in prompt
    assert "Uses short casual sentences." in prompt


def test_includes_summary_when_present():
    prompt = build_system_prompt(_game(), summary="They talked about work.")
    assert "Summary of the story so far" in prompt
    assert "They talked about work." in prompt


def test_always_includes_style_rules():
    prompt = build_system_prompt(_game(), summary="")
    assert "First person only" in prompt
    assert "never wrap your lines in quotation marks" in prompt.lower()


def test_omits_recalled_memories_when_absent():
    prompt = build_system_prompt(_game(), summary="")
    assert "Recalled memories" not in prompt


def test_includes_recalled_memories_when_present():
    prompt = build_system_prompt(_game(), summary="", recalled_memories=["Sam mentioned moving to Denver."])
    assert "Recalled memories" in prompt
    assert "Sam mentioned moving to Denver." in prompt


def test_omits_recalled_memories_when_empty_list():
    prompt = build_system_prompt(_game(), summary="", recalled_memories=[])
    assert "Recalled memories" not in prompt


def test_omits_followup_reason_when_absent():
    prompt = build_system_prompt(_game(), summary="")
    assert "checking back in" not in prompt


def test_includes_followup_reason_when_present():
    prompt = build_system_prompt(_game(), summary="", followup_reason="promised to ask how the exam went")
    assert "checking back in" in prompt
    assert "promised to ask how the exam went" in prompt


def test_voice_prompt_still_includes_persona_context():
    prompt = build_voice_system_prompt(_game(), summary="")
    assert "I am Sam, warm and sarcastic." in prompt
    assert "The user is Sam's old friend." in prompt


def test_voice_prompt_swaps_in_voice_rules_not_text_rules():
    prompt = build_voice_system_prompt(_game(), summary="")
    # VOICE_RULES asks for the opposite of text mode's RULES on quotes/parens.
    assert "never wrap your lines in quotation marks" not in prompt.lower()
    assert "speech segments" in prompt.lower()
    assert "delivery" in prompt.lower()


def test_text_prompt_unaffected_by_voice_prompt_existing():
    # Regression guard: build_system_prompt's default `rules` param must
    # still be text mode's RULES, not accidentally swapped.
    prompt = build_system_prompt(_game(), summary="")
    assert "never wrap your lines in quotation marks" in prompt.lower()
    assert "speech segments" not in prompt.lower()
