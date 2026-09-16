/** The glossy marble-sphere avatar used next to assistant messages - the
 * same teal/purple/pink/orange conic palette as HeroOrb (the Home page's
 * "Generate New Game" hero), so this reads as the same orb motif rather
 * than a one-off color scheme, just tuned dark to sit on the app's theme
 * instead of the light ref/chat.webp mockup it started from. */
export function OrbAvatar({ size = 40 }: { size?: number }) {
  return (
    <div
      className="shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        background: [
          "radial-gradient(circle at 30% 25%, rgba(255,255,255,0.55), rgba(255,255,255,0) 32%)",
          "conic-gradient(from 210deg at 50% 50%, #2dd4bf, #a855f7 30%, #ec4899 55%, #fb923c 78%, #2dd4bf 100%)",
        ].join(", "),
        boxShadow: "0 0 10px -2px rgba(168,85,247,0.5), inset 0 -3px 6px rgba(0,0,0,0.35)",
      }}
    />
  );
}
