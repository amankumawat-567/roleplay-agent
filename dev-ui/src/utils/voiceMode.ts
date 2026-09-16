import type { ModelsResponse } from "../types";

/** Ollama's own capability tag for a model with a real audio encoder -
 * mirrors llm/capabilities.py's AUDIO_INPUT_CAPABILITY. Confirmed live to
 * mean audio *input* (see docs/ARCHITECTURE.md's "Voice mode"), distinct
 * from the shipped TTS, which is chat-model-independent. */
const AUDIO_INPUT_CAPABILITY = "audio";

/** Whether `provider`/`model` (a persona's own fields) currently reports
 * audio-input capability in the capability cache - the single gate for
 * section F's voice mode switch (ChatPage) and Composer's dictation button
 * (F0/F1). False whenever `models` hasn't loaded yet, so voice mode never
 * flashes in before the cache is known. */
export function hasAudioInputCapability(provider: string, model: string, models: ModelsResponse | null): boolean {
  if (!models) return false;
  const match = models.providers.find((p) => p.provider === provider);
  const modelInfo = match?.models.find((m) => m.id === model);
  return !!modelInfo?.capabilities.includes(AUDIO_INPUT_CAPABILITY);
}
