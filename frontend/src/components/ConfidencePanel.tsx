import type { Confidence } from "../types";

/** Panel confidence + agreement, with a short read on what it means. */
export function ConfidencePanel({ confidence }: { confidence: Confidence | null }) {
  if (!confidence) return null;
  const c = confidence;
  const pct = Math.round(c.overall * 100);
  const color =
    c.label === "high" ? "var(--ok)" : c.label === "moderate" ? "var(--warn)" : "var(--danger)";

  return (
    <div className="card">
      <h2 data-idx="◆">Confidence</h2>
      <div className="conf-row">
        <div className="conf-dial">
          <div className="conf-val" style={{ color }}>{pct}%</div>
          <div className="conf-label" style={{ color }}>{c.label} confidence</div>
        </div>
        <div className="conf-bars">
          <Bar label="Panel agreement" value={c.panel_agreement} />
          <Bar label="Mean persona confidence" value={c.mean_persona_confidence} />
        </div>
      </div>
      <div className="subline" style={{ marginTop: 12 }}>
        {c.label === "high"
          ? "The six listeners largely agree — this prediction is well-supported."
          : c.label === "moderate"
          ? "Reasonable support, but the panel diverges on some beats (see the disagreement band on the curve)."
          : "Low support — the panel disagrees or agents dropped out. Treat as directional only."}
      </div>
    </div>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="conf-bar">
      <div className="conf-bar-head">
        <span>{label}</span>
        <span className="mono">{Math.round(value * 100)}%</span>
      </div>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
    </div>
  );
}
