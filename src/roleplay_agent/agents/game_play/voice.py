"""Voice mode's turn generation - F2, "the actual hard problem" (see
docs/ARCHITECTURE.md's "Voice mode"). A genuinely separate generation path from
agent.agent's `generate` node, not a post-processing step bolted onto the
existing streamed-text reply: text mode stays untouched (still prose,
still prompts.RULES, still richText.tsx's parsing), and a voice-mode turn
is structured output from the start.

Verified live from real usage, not assumed: `.with_structured_output()`
schema validity passing is not the same as content quality (the same
lesson game_builder.py's GameDraft needed real Field descriptions to
learn) - see this module's own tests plus a live check against this
project's real default model before relying on this in a shipped UI."""

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from roleplay_agent.agents.game_play.context import to_audio_message, to_lc_messages
from roleplay_agent.services.llm.registry import build_llm
from roleplay_agent.services.storage.models import Message


class SpeechSegment(BaseModel):
    """One spoken line, in the order it would be said - the audio
    equivalent of richText.tsx's splitIntoLines (several quoted segments
    in one reply becoming separate bubbles): synthesized separately and
    played with a natural gap between segments, not concatenated into one
    run-on utterance."""

    text: str = Field(
        description="The literal words spoken for this segment, and nothing else - no stage "
        "directions, no narration, no asterisks or parentheses. Just what is said out loud - "
        "including a real non-verbal sound the character actually makes, written as the sound "
        "itself ('haha', 'mmh', a sigh), and '...' for an actual pause or held breath, since "
        "only what's literally in these words is ever heard."
    )
    delivery: str | None = Field(
        default=None,
        description="A short, direct instruction for tone, pacing, emotion, or volume that "
        "changes how this segment sounds when spoken - cue it like a voice actor direction, e.g. "
        "'very happy and excited', 'voice dropping to a soft whisper', 'laughing as she says it', "
        "'breathless, almost moaning'. Never a repeat of the words in `text`, and never a "
        "substitute for an actual sound or pause that belongs in `text` instead - this only "
        "steers delivery, it can't manufacture a sound or silence that isn't in the words. Set it "
        "whenever tone/pacing/emotion genuinely colors the line; leave unset (null) only for a "
        "line said truly flat.",
    )


class VoiceTurn(BaseModel):
    """A persona's voice-mode reply - `agent/prompts.py`'s
    build_voice_system_prompt primes the model toward this shape.
    `segments` is never empty for a real reply; each `delivery` becomes
    `llm/tts.py`'s synthesize()'s own `instruct` param at speak time,
    never spoken text itself."""

    user_said: str = Field(
        description="A faithful transcript of what the user just said in the audio clip you "
        "were given, in their own words - not a summary, not a paraphrase, not a reply to it. "
        "This is the only record of what they said, since no separate speech-to-text step runs "
        "in voice mode (F0 - see docs/ARCHITECTURE.md's 'Voice mode') - it exists purely so this turn can be stored "
        "and recalled later, never spoken back to the user."
    )
    segments: list[SpeechSegment] = Field(
        description="One or more speech segments, in the order they would be spoken. Split a "
        "reply into multiple segments wherever the delivery genuinely changes between them - "
        "don't force everything into one segment just because it's a single reply."
    )


def generate_voice_turn(
    system_prompt: str,
    recent: list[Message],
    audio: bytes,
    provider: str,
    model: str,
    num_ctx: int,
    keep_alive: str,
) -> VoiceTurn:
    """`system_prompt` is expected to come from
    agent.prompts.build_voice_system_prompt, not build_system_prompt -
    VoiceTurn's shape only makes sense paired with VOICE_RULES' framing.
    `audio` is the current turn's raw mic capture (WAV bytes) - `recent`
    only ever carries *prior* turns as text (this session's own persisted
    `user_said`/segment-text history), never raw audio, so this is a
    deliberately separate parameter rather than something to synthesize
    from `recent` alone.

    A parallel generation path to agent.agent.RoleplayAgent's LangGraph
    `_generate` node, not a route through it (see this module's own
    docstring for why F2 already made that call) - `ChatState` itself stays
    text-only; this function is where a turn's audio actually lives."""
    llm = build_llm(provider, model, num_ctx, keep_alive)
    messages: list[BaseMessage] = to_lc_messages(system_prompt, recent)
    messages.append(to_audio_message(audio))
    structured_llm = llm.with_structured_output(VoiceTurn)
    return structured_llm.invoke(messages)
