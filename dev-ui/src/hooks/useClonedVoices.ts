import { useEffect, useState } from "react";
import { api } from "../services/api";

/** Voice ids discovered off data/voice_samples/ (see GET /api/voices/cloned) -
 * shared between AudioPage and GameEditorPage's VoicePicker so both learn
 * about a newly dropped-in cloned voice without a hardcoded entry in
 * dev-ui/src/data/voices.ts. Best-effort: nothing usable yet (backend
 * unreachable, or the dir doesn't exist) just means no custom voices show,
 * not a page-level error. */
export function useClonedVoices(): string[] {
  const [voices, setVoices] = useState<string[]>([]);

  useEffect(() => {
    api
      .getClonedVoices()
      .then((res) => setVoices(res.voices))
      .catch(() => {});
  }, []);

  return voices;
}
