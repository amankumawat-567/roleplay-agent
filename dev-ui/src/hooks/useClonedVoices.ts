import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { ClonedVoiceInfo } from "../types";

/** Cloned voices discovered off data/voice_samples/ (see GET /api/voices/cloned) -
 * shared between AudioPage and GameEditorPage's VoicePicker so both learn
 * about a newly added cloned voice without a hardcoded entry in
 * dev-ui/src/data/voices.ts. Best-effort: nothing usable yet (backend
 * unreachable, or the dir doesn't exist) just means no custom voices show,
 * not a page-level error. */
export function useClonedVoices(): ClonedVoiceInfo[] {
  const [voices, setVoices] = useState<ClonedVoiceInfo[]>([]);

  useEffect(() => {
    api
      .getClonedVoices()
      .then((res) => setVoices(res.voices))
      .catch(() => {});
  }, []);

  return voices;
}
