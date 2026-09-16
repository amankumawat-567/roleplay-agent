import { avatarDataUri } from "../utils/avatar";

/** A real, distinctive character avatar per persona (DiceBear, seeded by
 * id) - deterministic and algorithmic, not AI-generated and not a flat
 * gradient/orb. Used anywhere a persona needs a "face": cards, the AI
 * builder's own hero, etc. */
export function PersonaAvatar({
  id,
  size = 64,
  ringClassName = "ring-white/15",
}: {
  id: string;
  size?: number;
  ringClassName?: string;
}) {
  return (
    <img
      src={avatarDataUri(id)}
      alt=""
      width={size}
      height={size}
      className={`shrink-0 rounded-full bg-white/10 ring-2 ${ringClassName}`}
      style={{ width: size, height: size }}
    />
  );
}
