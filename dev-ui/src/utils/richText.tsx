import type { ReactNode } from "react";

/** The model is instructed never to wrap lines in quotes, but as a fallback:
 * if a reply comes back as several "..." segments, treat each as its own
 * line (that's what several quoted sentences in one reply means) instead of
 * showing the raw quote marks in one paragraph. */
export function splitIntoLines(text: string): string[] {
  const trimmed = text.trim();
  const quoted = [...trimmed.matchAll(/"([^"]+)"/g)];
  if (quoted.length > 1) return quoted.map((m) => m[1].trim()).filter(Boolean);
  if (quoted.length === 1 && quoted[0][0].length >= trimmed.length - 2) {
    return [quoted[0][1].trim()];
  }
  return trimmed ? [trimmed] : [];
}

/** **bold** -> <strong>, *emphasis* -> <em>. Built as React nodes (never
 * dangerouslySetInnerHTML), so anything else in the text renders as plain,
 * auto-escaped text - safe even though it's model output. */
export function renderRichText(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

export function timeAgoGroup(unixSeconds: number): "Today" | "Yesterday" | "Earlier" {
  const now = new Date();
  const date = new Date(unixSeconds * 1000);
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return "Earlier";
}
