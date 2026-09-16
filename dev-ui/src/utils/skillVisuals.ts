import type { LucideIcon } from "lucide-react";
import { AlarmClock, Globe, Puzzle } from "lucide-react";
import { colorsFor } from "./gradient";

/** Unlike a persona's icon (gameTileVisuals.ts' `iconFor`, a deterministic
 * but arbitrary hash), a skill is a specific tool with its own identity -
 * so its "logo" is a fixed, hand-picked icon per skill id, not a hash. A
 * skill that hasn't been given one yet falls back to a generic puzzle
 * piece rather than a random glyph, since there's nothing to be random
 * about: the same tool should always look the same. */
const SKILL_ICONS: Record<string, LucideIcon> = {
  web_research: Globe,
  schedule_followup: AlarmClock,
};

const SKILL_ACCENTS: Record<string, string> = {
  web_research: "#2563eb",
  schedule_followup: "#f97316",
};

export function iconForSkill(id: string): LucideIcon {
  return SKILL_ICONS[id] ?? Puzzle;
}

export function accentForSkill(id: string): string {
  return SKILL_ACCENTS[id] ?? colorsFor(id)[0];
}
