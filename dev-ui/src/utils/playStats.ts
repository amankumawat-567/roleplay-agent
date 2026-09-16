/** "Today", "Yesterday", "5d ago", or a short date once it's old enough
 * that a relative count stops being useful. */
export function formatLastPlayed(unixSeconds: number): string {
  const days = Math.floor((Date.now() - unixSeconds * 1000) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 14) return `${days}d ago`;
  return new Date(unixSeconds * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Rounds a played-time span down to whichever unit reads best - minutes
 * under an hour, hours (one decimal) beyond that. */
export function formatPlayedTime(seconds: number): string {
  if (seconds < 60) return "<1m";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}
