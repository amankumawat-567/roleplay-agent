import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";

// The backend only sweeps for due follow-ups every ~30s (see
// agent/followups.py's POLL_INTERVAL_SECONDS), so delivery can lag a
// countdown hitting zero by that much - grace-poll every few seconds
// past zero rather than assuming it landed instantly.
const GRACE_POLL_MS = 5000;

/** Polls for the session's next scheduled check-back (see
 * agent/followups.py) and ticks a countdown down to it client-side - no
 * WebSocket/SSE, per docs/roadmap.md's single-user "simplest thing that
 * works" scope reminder. Once the countdown hits zero, it grace-polls
 * until the pending entry actually clears, then calls `onDelivered` so
 * the caller can re-fetch messages.
 *
 * `refreshSignal` re-runs the schedule check whenever it changes - without
 * it, a follow-up scheduled *after* this hook first mounted (i.e. any time
 * the persona says "I'll check back" mid-conversation, not just one already
 * pending on page load) would never be noticed, since nothing else here
 * ever asks the server again. Pass something that changes once per
 * finished turn (e.g. the caller's `streaming` flag). */
export function useFollowupCountdown(sessionId: string, onDelivered: () => void, refreshSignal?: unknown) {
  const [fireAt, setFireAt] = useState<number | null>(null);
  const [remainingMs, setRemainingMs] = useState<number | null>(null);
  const onDeliveredRef = useRef(onDelivered);
  onDeliveredRef.current = onDelivered;

  const refreshSchedule = useCallback(async () => {
    try {
      const res = await api.getScheduledFollowup(sessionId);
      setFireAt(res.fire_at);
    } catch {
      // Best-effort - just try again on the next poll.
    }
  }, [sessionId]);

  useEffect(() => {
    refreshSchedule();
    // refreshSignal is intentionally in the dep list purely to retrigger
    // this effect - its value is never read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSchedule, refreshSignal]);

  useEffect(() => {
    if (fireAt == null) {
      setRemainingMs(null);
      return;
    }

    let graceElapsedMs = 0;
    const id = setInterval(async () => {
      const remaining = fireAt * 1000 - Date.now();
      setRemainingMs(remaining);
      if (remaining > 0) return;

      graceElapsedMs += 1000;
      if (graceElapsedMs < GRACE_POLL_MS) return;
      graceElapsedMs = 0;

      const res = await api.getScheduledFollowup(sessionId).catch(() => null);
      if (res && res.fire_at === fireAt) return; // not delivered yet, keep grace-polling
      setFireAt(res?.fire_at ?? null);
      onDeliveredRef.current();
    }, 1000);

    return () => clearInterval(id);
  }, [fireAt, sessionId]);

  return { remainingMs };
}
