const PALETTE: [string, string][] = [
  ["#7c3aed", "#db2777"],
  ["#2563eb", "#7c3aed"],
  ["#0891b2", "#4338ca"],
  ["#be185d", "#f97316"],
  ["#059669", "#0891b2"],
  ["#9333ea", "#e11d48"],
];

export function hash(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i++) h = (h * 31 + input.charCodeAt(i)) >>> 0;
  return h;
}

/** The raw [from, to] hex pair a persona's gradient is built from - reused
 * anywhere that needs the actual colors (e.g. an orb's radial glow), not
 * just a CSS gradient string. */
export function colorsFor(id: string): [string, string] {
  return PALETTE[hash(id) % PALETTE.length];
}

/** A deterministic two-color gradient per id, so persona cards look
 * visually distinct without needing uploaded cover art. */
export function gradientFor(id: string): string {
  const [from, to] = colorsFor(id);
  return `linear-gradient(135deg, ${from}, ${to})`;
}
