/** Formats milliseconds as "m:ss" for a scheduled check-back countdown -
 * shared by ChatPage's header badge and VoiceCallPage's equivalent so the
 * two modes read identically. */
export function formatCountdown(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
