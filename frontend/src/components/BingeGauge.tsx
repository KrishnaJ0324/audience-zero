/**
 * Binge Probability gauge (§2.10 / P5 "Cliffhanger Optimizer").
 *
 * A semicircular instrument dial reading the likelihood a listener presses play
 * on the next episode — driven by the final-beat hook, binge-weighted across
 * personas. Styled as an editorial measurement dial, not a neon widget.
 */
export function BingeGauge({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value));
  const R = 76;
  const CX = 100;
  const CY = 96;
  const len = Math.PI * R; // semicircle arc length
  const fill = v * len;

  const color =
    v >= 0.66 ? "var(--ok)" : v >= 0.4 ? "var(--warn)" : "var(--danger)";
  const band = v >= 0.66 ? "STRONG HOOK" : v >= 0.4 ? "SOFT HOOK" : "WEAK HOOK";

  // needle angle: 180° (left) → 0° (right)
  const angle = Math.PI * (1 - v);
  const nx = CX + (R - 10) * Math.cos(angle);
  const ny = CY - (R - 10) * Math.sin(angle);

  return (
    <div className="binge-gauge">
      <svg viewBox="0 0 200 120" width="176" height="106" aria-label="binge probability">
        {/* tick marks at 0 / 25 / 50 / 75 / 100 */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const a = Math.PI * (1 - t);
          const x1 = CX + R * Math.cos(a);
          const y1 = CY - R * Math.sin(a);
          const x2 = CX + (R + 7) * Math.cos(a);
          const y2 = CY - (R + 7) * Math.sin(a);
          return <line key={t} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--rule-strong)" strokeWidth={1} />;
        })}
        <path
          d={`M${CX - R},${CY} A${R},${R} 0 0 1 ${CX + R},${CY}`}
          fill="none"
          stroke="var(--rule)"
          strokeWidth={12}
        />
        <path
          d={`M${CX - R},${CY} A${R},${R} 0 0 1 ${CX + R},${CY}`}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeDasharray={`${fill} ${len - fill}`}
          strokeLinecap="butt"
        />
        <line x1={CX} y1={CY} x2={nx} y2={ny} stroke="var(--ink)" strokeWidth={2} />
        <circle cx={CX} cy={CY} r={4} fill="var(--ink)" />
        <text x={CX} y={CY - 22} textAnchor="middle" className="bg-val">
          {Math.round(v * 100)}%
        </text>
      </svg>
      <div className="bg-caption">
        <span className="bg-label">Binge Probability</span>
        <span className="bg-band" style={{ color }}>
          {band}
        </span>
      </div>
    </div>
  );
}
