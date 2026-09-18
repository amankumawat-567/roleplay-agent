"""Voice mode's turn generation - F2, "the actual hard problem" (see
docs/ARCHITECTURE.md's "Voice mode"). A genuinely separate generation path from
agent.agent's `generate` node, not a post-processing step bolted onto the
existing streamed-text reply: text mode stays untouched (still prose,
still prompts.RULES, still richText.tsx's parsing), and a voice-mode turn
is structured output from the start.

Two input paths, depending on whether this turn's model can actually take
audio (`llm/capabilities.py`'s AUDIO_INPUT_CAPABILITY): a capable model
hears the raw clip directly and produces both `user_said` and `segments`
from it in one call (F0's original "no separate speech-to-text step").
Every other model - hosted providers, non-audio Ollama models - gets the
clip transcribed locally first (`services/stt/stt.py`), and only the
resulting text is sent; `user_said` is then just that transcript, not
something the model has to produce. `api/routes/gameplay/chat.py`'s
`/voice-turn` decides which path a given turn takes.

Verified live from real usage, not assumed: `.with_structured_output()`
schema validity passing is not the same as content quality (the same
lesson game_builder.py's GameDraft needed real Field descriptions to
learn) - see this module's own tests plus a live check against this
project's real default model before relying on this in a shipped UI."""

from langchain_core.messages import BaseMessage, HumanMessage
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
        "This is the only record of what they said - it exists purely so this turn can be stored "
        "and recalled later, never spoken back to the user."
    )
    segments: list[SpeechSegment] = Field(
        description="One or more speech segments, in the order they would be spoken. Split a "
        "reply into multiple segments wherever the delivery genuinely changes between them - "
        "don't force everything into one segment just because it's a single reply."
    )


class VoiceReply(BaseModel):
    """The transcript-input counterpart to VoiceTurn: used when this turn's
    audio was already transcribed locally (see this module's docstring) -
    `user_said` is already known at that point, so only the spoken reply
    itself is asked of the model."""

    segments: list[SpeechSegment] = Field(
        description="One or more speech segments, in the order they would be spoken. Split a "
        "reply into multiple segments wherever the delivery genuinely changes between them - "
        "don't force everything into one segment just because it's a single reply."
    )


def generate_voice_turn(
    system_prompt: str,
    recent: list[Message],
    provider: str,
    model: str,
    num_ctx: int,
    keep_alive: str,
    audio: bytes | None = None,
    transcript: str | None = None,
    enable_thinking: bool | None = None,
) -> VoiceTurn:
    """`system_prompt` is expected to come from
    agent.prompts.build_voice_system_prompt, not build_system_prompt -
    VoiceTurn's shape only makes sense paired with VOICE_RULES' framing.
    `recent` only ever carries *prior* turns as text (this session's own
    persisted `user_said`/segment-text history), never raw audio, so the
    current turn's input is always a separate parameter rather than
    something to synthesize from `recent` alone.

    Exactly one of `audio` (the current turn's raw mic capture, WAV bytes)
    or `transcript` (already transcribed locally - see this module's
    docstring) is given, matching whichever path
    `api/routes/gameplay/chat.py`'s `/voice-turn` chose for this turn's
    model. The `audio` branch asks the model for the full VoiceTurn schema
    (it produces `user_said` itself, hearing the clip); the `transcript`
    branch already knows `user_said`, so it only asks for VoiceReply's
    `segments` and wraps the given transcript back in as `user_said`.

    A parallel generation path to agent.agent.RoleplayAgent's LangGraph
    `_generate` node, not a route through it (see this module's own
    docstring for why F2 already made that call) - `ChatState` itself stays
    text-only; this function is where a turn's audio/transcript actually
    lives."""
    llm = build_llm(provider, model, num_ctx, keep_alive, reasoning=enable_thinking)
    messages: list[BaseMessage] = to_lc_messages(system_prompt, recent)

    if audio is not None:
        messages.append(to_audio_message(audio))
        structured_llm = llm.with_structured_output(VoiceTurn)
        return structured_llm.invoke(messages)

    messages.append(HumanMessage(content=transcript))
    structured_llm = llm.with_structured_output(VoiceReply)
    reply: VoiceReply = structured_llm.invoke(messages)
    return VoiceTurn(user_said=transcript, segments=reply.segments)
