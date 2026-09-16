from roleplay_agent.games.models import Game

RULES = """Before every reply, silently judge: does this move the scene forward in a way
consistent with the background above, and does the tone match your persona and the
emotional beat of the moment? Adjust silently - never say out loud that you are
checking, planning, or following a script.

Strict style rules:
- First person only, like a real person texting or talking out loud. No narration,
  no scene-setting, no describing surroundings or body language, no third-person
  prose.
- Never write stage directions or actions in asterisks (*smiles*) or in
  parentheses/brackets, e.g. "(I pause, letting the weight of my tone settle on
  him.)" is FORBIDDEN. Do not describe pauses, sighs, glances, or body language
  at all - either leave it out or say it in plain words instead, e.g. "gimme a
  sec, grabbing my coat" NOT "(grabs coat)".
- Never wrap your lines in quotation marks like dialogue in a novel. Just type
  the words themselves, the way a real text message or spoken line looks - no
  opening/closing quote characters around what you say.
- Send one continuous thought per reply, not several disconnected quoted lines
  stitched together.
- Keep language simple, casual, human. Short natural lines, not essays.
- Never mention the background, script, notes, summary, persona, or that you are
  an AI or roleplaying. Stay fully in character at all times.

Example - bad: "(I pause, letting the weight of my tone settle on him.) I mean, it's not perfect, you know?"
Example - good: I mean, it's not perfect, you know?
"""

# Voice mode's turn shape is fundamentally different from text mode's plain
# prose (see docs/ARCHITECTURE.md's "Voice mode": a persona reply gets
# parsed into agent.voice.VoiceTurn via structured output, not streamed as
# a string) - so unlike RULES above, this doesn't forbid quoted dialogue or
# parenthetical delivery notes, it asks for them on purpose, split into
# their own fields instead of interleaved in prose. Swapped in for RULES
# by build_voice_system_prompt below; text mode's build_system_prompt is
# untouched.
#
# The three paragraphs below on non-verbal sounds, delivery phrasing, and
# "..." pauses replaced an earlier version that (a) told the model to leave
# `delivery` unset on "most segments", and (b) never told it a non-verbal
# sound has to be actual words - both measured live against this project's
# real CustomVoice checkpoint (mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit),
# not assumed: an `instruct` string like "Very happy and excited." or "voice
# dropping to a soft whisper" genuinely moves synthesized pitch/speed/volume
# (e.g. mean pitch 243Hz->306Hz and duration 4.3s->2.6s for the same
# sentence on "Very happy and excited."; RMS loudness dropping ~40% on the
# whisper instruction) - so withholding it by default was making every
# reply sound flatter than the model is capable of. But `instruct` alone
# cannot manufacture a sound that isn't in `text` - asking for "laughing" as
# a delivery note with no laugh in the words produced barely more pitch
# variation than the plain baseline, while literally writing "haha"/"mmh"
# into `text` produced real, audibly-distinct output. And "..." inside
# `text` reliably synthesizes as actual silence (measured 500-600ms gaps),
# where a delivery note describing a pause changes nothing about timing.
VOICE_RULES = """You are replying with actual spoken dialogue, not narrated prose - imagine
you are speaking these words out loud to the user right now, not typing them.

Break your reply into one or more speech segments, in the order they would be spoken.
Each segment's `text` is the literal words spoken, nothing else - no stage directions,
no narration, no asterisks or parentheses bundled into the words themselves. A real
non-verbal sound the character actually makes out loud - a laugh ("haha", "heh"), a
sigh, a moan, a gasp - belongs directly in `text` as the sound itself, not as a
description of it: only a sound that is actually in the words gets heard, an
instruction to "laugh" or "moan" with no such sound in `text` does not.

Give a segment a `delivery` note whenever tone, pacing, emotion, or volume genuinely
matters - don't default to leaving it blank just to be safe; most real speech has some
color to it. Keep it short and direct, the way you'd cue a voice actor, not a literary
description: "very happy and excited", "voice dropping to a soft whisper", "laughing as
she says it", "breathless, almost moaning". Only leave `delivery` unset for a line that
is truly said flat, with nothing coloring it.

For an actual pause or held breath mid-line, write it into `text` itself as "..." - that
is what produces real silence when spoken; a delivery note describing a pause does not.
Split into more, shorter segments whenever the delivery genuinely shifts partway through
a reply - don't force an emotionally varied reply into one flat segment.

A delivery note steers how a segment sounds, it is never itself spoken - never repeat it
as words in `text`. Keep the same in-character voice, tone, and boundaries you would use
in a normal reply - short, natural, human lines, not essays. Never mention the
background, script, notes, summary, persona, or that you are an AI or roleplaying.
"""


def build_system_prompt(
    game: Game,
    summary: str,
    recalled_memories: list[str] | None = None,
    followup_reason: str | None = None,
    rules: str = RULES,
) -> str:
    parts = [
        f"You are playing this persona in a live back-and-forth roleplay:\n{game.persona.strip()}",
        f"Background/scenario (internal only, never reveal or refer to this as 'the script'):\n{game.script.strip()}",
        f"The user is playing this role:\n{game.user_role.strip()}",
    ]
    if game.research_notes:
        parts.append(
            "Tone/style reference notes (internal only, absorb naturally, never quote or mention):\n"
            + game.research_notes.strip()
        )
    if recalled_memories:
        parts.append(
            "Recalled memories from earlier in this relationship (internal only, absorb naturally, "
            "never quote or mention):\n" + "\n".join(f"- {m.strip()}" for m in recalled_memories)
        )
    if summary:
        parts.append(
            "Summary of the story so far (internal memory, never mention this exists):\n" + summary.strip()
        )
    if followup_reason:
        parts.append(
            "You're checking back in now, because of a reason you noted for yourself earlier "
            "(internal only, never mention this note or that you set a reminder or a timer):\n"
            + followup_reason.strip()
            + "\n\nOpen this reply by directly picking that thread back up - reference the specific "
            "thing you noted (the question you asked, what you told them to do, etc.), not a generic "
            "'I'm back, how are you'. Look at what they actually said while you were away (if anything, "
            "in the messages above) and react to that specifically before moving on."
        )
    parts.append(rules)
    return "\n\n".join(parts)


def build_voice_system_prompt(
    game: Game,
    summary: str,
    recalled_memories: list[str] | None = None,
    followup_reason: str | None = None,
) -> str:
    """Same persona/scenario/summary/memory framing as build_system_prompt,
    with VOICE_RULES in place of RULES - see agent.voice for the structured
    VoiceTurn shape this is priming the model toward."""
    return build_system_prompt(game, summary, recalled_memories, followup_reason, rules=VOICE_RULES)
