import { useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";
import type { CalibrationSummary } from "../types";

/**
 * Calibration (§ P5 defense: "your data makes it sharper"). Attach real
 * post-publish retention (or simulate a sample) and overlay predicted-vs-actual,
 * with the calibration state + error made explicit.
 */
export function CalibrationOverlay({
  runId,
  calibration,
  readOnly,
}: {
  runId: string;
  calibration: CalibrationSummary | null;
  readOnly?: boolean;
}) {
  const [cal, setCal] = useState<CalibrationSummary | null>(calibration);
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const state = cal ?? calibration;
  const calibrated = state?.state === "calibrated" && state.actual_retention;

  const run = async (fn: () => Promise<CalibrationSummary>) => {
    setBusy(true); setErr(null);
    try { setCal(await fn()); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const attach = () => {
    const nums = raw.replace(/,/g, " ").split(/\s+/).map(Number).filter((x) => !isNaN(x));
    if (!nums.length) { setErr("Enter per-beat retention numbers (0–1 or %)."); return; }
    run(() => api.calibrate(runId, nums));
  };

  const data =
    calibrated && state
      ? (state.predicted_retention ?? []).map((p, i) => ({
          beat: `B${i + 1}`,
          predicted: Math.round((p ?? 0) * 100),
          actual: Math.round((state.actual_retention?.[i] ?? 0) * 100),
        }))
      : [];

  return (
    <div className="card">
      <h2 data-idx="◇">
        Calibration
        <span className={`cal-chip ${calibrated ? "on" : ""}`}>
          {calibrated ? "calibrated" : "uncalibrated"}
        </span>
      </h2>

      {!calibrated && (
        <div>
          <div className="subline" style={{ marginBottom: 14 }}>
            Feed in the episode's real post-publish retention to grade the
            prediction — the panel gets sharper as you do. No real data yet? Simulate a sample.
          </div>
          {!readOnly && (
            <>
              <div className="row">
                <input
                  type="text"
                  placeholder="Per-beat retention, e.g. 100 88 82 … or 1.0 0.88 …"
                  value={raw}
                  onChange={(e) => setRaw(e.target.value)}
                  style={{ flex: 1, minWidth: 200 }}
                />
                <button className="ghost" onClick={attach} disabled={busy}>Attach actual</button>
              </div>
              <div className="row" style={{ marginTop: 10 }}>
                <button className="primary" onClick={() => run(() => api.simulateCalibration(runId))} disabled={busy}>
                  {busy ? "Calibrating…" : "⊹ Simulate a sample"}
                </button>
              </div>
            </>
          )}
          {err && <div className="error" style={{ marginTop: 10 }}>⚠ {err}</div>}
        </div>
      )}

      {calibrated && state && (
        <div>
          <div className="metrics" style={{ marginTop: 0, marginBottom: 16 }}>
            <div className="metric">
              <div className="v" style={{ color: maeColor(state.mae) }}>
                {state.mae != null ? `${(state.mae * 100).toFixed(1)}%` : "—"}
              </div>
              <div className="k">mean abs error</div>
            </div>
            <div className="metric">
              <div className="v" style={{ color: "var(--ok)" }}>
                {state.correlation != null ? state.correlation.toFixed(2) : "—"}
              </div>
              <div className="k">correlation</div>
            </div>
          </div>
          <div className="chart-wrap" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 12, right: 16, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="beat" tick={{ fill: "var(--muted-2)", fontSize: 11, fontFamily: "var(--mono)" }} axisLine={{ stroke: "var(--border)" }} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: "var(--muted-2)", fontSize: 11, fontFamily: "var(--mono)" }} axisLine={false} tickLine={false} width={44} />
                <Tooltip contentStyle={{ background: "var(--panel-2)", border: "1px solid var(--border-glow)", borderRadius: 10, fontSize: 12, fontFamily: "var(--mono)" }} />
                <Legend wrapperStyle={{ fontSize: 12, fontFamily: "var(--mono)" }} />
                <Line type="monotone" dataKey="predicted" name="Predicted" stroke="var(--ink)" strokeWidth={2.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="actual" name="Actual" stroke="var(--ok)" strokeWidth={3} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="subline" style={{ marginTop: 10 }}>
            {state.mae != null && state.mae < 0.1
              ? "The panel tracked the real audience closely — this prediction is well-calibrated."
              : "Notable gap between predicted and actual — feed more episodes to sharpen the panel."}
          </div>
        </div>
      )}
    </div>
  );
}

const maeColor = (mae: number | null | undefined) =>
  mae == null ? "var(--muted)" : mae < 0.1 ? "var(--ok)" : mae < 0.2 ? "var(--warn)" : "var(--danger)";
