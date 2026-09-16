import type { CSSProperties } from "react";

interface Particle {
  left: string;
  delay: string;
  duration: string;
  size: number;
  drift: string;
}

const PARTICLES: Particle[] = [
  { left: "8%", delay: "0s", duration: "5.5s", size: 4, drift: "10px" },
  { left: "22%", delay: "1.8s", duration: "6.5s", size: 3, drift: "-14px" },
  { left: "38%", delay: "0.6s", duration: "5s", size: 5, drift: "8px" },
  { left: "58%", delay: "2.6s", duration: "7s", size: 3, drift: "-10px" },
  { left: "72%", delay: "1.2s", duration: "6s", size: 4, drift: "12px" },
  { left: "88%", delay: "3.2s", duration: "5.8s", size: 3, drift: "-8px" },
];

/** Sparkles rising out of the hero orb's footprint and fading as they go -
 * purely decorative, absolutely positioned within a relative parent. */
export function FloatingParticles() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-visible">
      {PARTICLES.map((p, i) => (
        <span
          key={i}
          className="animate-float-particle absolute bottom-0 rounded-full bg-white"
          style={
            {
              left: p.left,
              width: p.size,
              height: p.size,
              animationDelay: p.delay,
              animationDuration: p.duration,
              boxShadow: "0 0 6px 1px rgba(255,255,255,0.7)",
              "--drift": p.drift,
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
