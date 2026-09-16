export interface Voice {
  id: string;
  name: string;
  style: string;
  /** [from, to] gradient pair for the card's glow and detail-rail accent -
   * the avatar's own background comes from its vendored SVG instead (see
   * VoiceAvatar). */
  colors: [string, string];
}

/** A short pre-generated sample clip for a voice, for quick preview on this
 * page - not synthesized live (that's what POST /api/sessions/{id}/speak
 * is for, see docs/ARCHITECTURE.md's "Local text-to-speech"). Served
 * straight off data/voice_samples/ (see main.py's /media/voice-samples
 * mount), same pattern as a game's cover image - not copied into this
 * frontend's own public/. */
export function sampleUrlFor(id: string): string {
  return `/media/voice-samples/${id}.wav`;
}

/** CustomVoice preset speakers a persona can be assigned (Game.voice, see
 * GameEditorPage's VoicePicker) - verified against the real model's own
 * speaker list, not the wrapper repo's (which named two speakers, "Ethan"
 * and "Chelsie", that don't actually exist on the model). A curated
 * subset of the real 9, not all of them - must stay in sync with the
 * backend's services.tts.tts.SUPPORTED_VOICES, see docs/ARCHITECTURE.md's
 * "Local text-to-speech". */
export const VOICES: Voice[] = [
  {
    id: "ryan",
    name: "Ryan",
    style: "Warm & upbeat",
    colors: ["#2563eb", "#7c3aed"],
  },
  {
    id: "aiden",
    name: "Aiden",
    style: "Calm & steady",
    colors: ["#0891b2", "#4338ca"],
  },
  {
    id: "dylan",
    name: "Dylan",
    style: "Easygoing & casual",
    colors: ["#059669", "#0891b2"],
  },
  {
    id: "serena",
    name: "Serena",
    style: "Smooth & soothing",
    colors: ["#e11d48", "#f97316"],
  },
  {
    id: "vivian",
    name: "Vivian",
    style: "Playful & expressive",
    colors: ["#db2777", "#9333ea"],
  },
];
