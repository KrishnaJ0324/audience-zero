import type { ReactNode } from "react";

/**
 * Decorative layer. Every shape here derives from the brand reticle (concentric
 * rings + crosshair) or the attention curve the product actually plots, so the
 * ornament reads as one family rather than random noise.
 *
 * Nothing in this file is interactive: the whole layer is aria-hidden and
 * pointer-events:none, and all motion sits behind prefers-reduced-motion.
 */
export function Decor() {
  return (
    <div className="decor" aria-hidden="true">
      <div className="decor-grid" />
      <span className="decor-blob decor-blob--a" />
      <span className="decor-blob decor-blob--b" />
      <span className="decor-blob decor-blob--c" />
      <Reticle className="decor-reticle decor-reticle--tr" />
      <Reticle className="decor-reticle decor-reticle--bl" />
    </div>
  );
}

/** Concentric rings + crosshair — the brand mark, blown up as texture. */
function Reticle({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 200 200" fill="none" aria-hidden="true">
      <circle cx="100" cy="100" r="96" stroke="currentColor" strokeWidth="0.8" />
      <circle cx="100" cy="100" r="70" stroke="currentColor" strokeWidth="0.8" />
      <circle cx="100" cy="100" r="44" stroke="currentColor" strokeWidth="0.8" />
      <circle cx="100" cy="100" r="18" stroke="currentColor" strokeWidth="0.8" />
      <circle cx="100" cy="100" r="70" stroke="currentColor" strokeWidth="6" strokeDasharray="1 9" strokeLinecap="round" opacity="0.7" />
      <path d="M100 0v34M100 166v34M0 100h34M166 100h34" stroke="currentColor" strokeWidth="0.8" />
    </svg>
  );
}

/** Hero-side art: a reticle behind the attention curve the panel produces. */
export function HeroArt() {
  return (
    <svg className="hero-art" viewBox="0 0 260 180" fill="none" aria-hidden="true">
      <g className="ha-rings">
        <circle cx="196" cy="62" r="56" stroke="var(--accent)" strokeWidth="1" opacity="0.22" />
        <circle cx="196" cy="62" r="38" stroke="var(--accent)" strokeWidth="1" opacity="0.3" />
        <circle cx="196" cy="62" r="20" stroke="var(--accent)" strokeWidth="1" opacity="0.4" />
        <circle cx="196" cy="62" r="4" fill="var(--accent)" opacity="0.55" />
      </g>

      {/* beat grid */}
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line
          key={i}
          x1={22 + i * 40}
          y1="34"
          x2={22 + i * 40}
          y2="150"
          stroke="var(--rule-strong)"
          strokeWidth="1"
          opacity="0.5"
        />
      ))}
      <line x1="14" y1="150" x2="248" y2="150" stroke="var(--rule-strong)" strokeWidth="1" />

      {/* attention curve + the dip the panel is looking for */}
      <path
        className="ha-curve"
        d="M18 62 C 48 50, 66 58, 88 74 S 118 126, 142 112 S 186 66, 214 58 L 238 54"
        stroke="var(--accent)"
        strokeWidth="2.4"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M18 62 C 48 50, 66 58, 88 74 S 118 126, 142 112 S 186 66, 214 58 L 238 54 L 238 150 L 18 150 Z"
        fill="url(#haFade)"
      />
      <circle className="ha-dip" cx="136" cy="118" r="5.5" fill="var(--danger)" />
      <circle cx="136" cy="118" r="11" stroke="var(--danger)" strokeWidth="1" opacity="0.4" />

      {/* persona dots reading along the timeline */}
      {[
        { x: 62, y: 44, c: "var(--accent-2)" },
        { x: 106, y: 92, c: "var(--warn)" },
        { x: 190, y: 66, c: "var(--ok)" },
      ].map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r="3.5" fill={d.c} opacity="0.85" />
      ))}

      <defs>
        <linearGradient id="haFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/** Illustrated placeholder for "there is nothing here yet" spots. */
export function EmptyNote({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty-note">
      <svg viewBox="0 0 120 72" fill="none" aria-hidden="true">
        <rect
          x="0.75" y="0.75" width="118.5" height="70.5" rx="9"
          stroke="var(--rule-strong)" strokeWidth="1.5" strokeDasharray="5 5"
        />
        <path
          d="M14 46 C 30 46, 32 26, 46 26 S 62 50, 76 44 S 96 22, 106 26"
          stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" opacity="0.5"
        />
        <circle cx="46" cy="26" r="3" fill="var(--accent)" opacity="0.7" />
        <circle cx="76" cy="44" r="3" fill="var(--accent-2)" opacity="0.7" />
        <path d="M14 58h92" stroke="var(--rule)" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <div>
        <b>{title}</b>
        {children && <span>{children}</span>}
      </div>
    </div>
  );
}
