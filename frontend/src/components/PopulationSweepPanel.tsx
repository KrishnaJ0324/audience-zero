import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { PopulationSweep } from "../types";

/**
 * Population Sweep (§2.10, stretch) — extrapolate the 6 calibrated archetypes to
 * a crowd of ~200 sampled listeners and plot where that crowd drops off. Opt-in
 * and independent of the golden path; deterministic in mock mode.
 */
export function PopulationSweepPanel({ runId }: { runId: string }) {
  const [sweep, setSweep] = useState<PopulationSweep | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      setSweep(await api.sweep(runId, 200));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  // deep-link affordance: /?run=...&sweep=1 auto-runs the sweep once
  const auto = useRef(false);
  useEffect(() => {
    if (auto.current) return;
    if (new URLSearchParams(window.location.search).get("sweep") === "1") {
      auto.current = true;
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const max = sweep ? Math.max(1, ...sweep.drop_histogram) : 1;

  return (
    <div className="card fade-in">
      <h2 data-idx="07">
        Population Sweep<span className="note">extrapolated crowd · stretch</span>
      </h2>

      {!sweep && (
        <div>
          <div className="subline" style={{ marginBottom: 14 }}>
            Sample ~200 listeners with taste-seeds jittered around the six
            archetypes and plot where the crowd drops off — the "thousands of AI
            users" view. Deterministic; the golden path never depends on it.
          </div>
          <button className="primary" onClick={run} disabled={busy}>
            {busy ? "Sampling 200 listeners…" : "⊹ Run Population Sweep"}
          </button>
          {err && <div className="error" style={{ marginTop: 10 }}>⚠ {err}</div>}
        </div>
      )}

      {sweep && (
        <div>
          <div className="metrics" style={{ marginTop: 0, marginBottom: 18 }}>
            <div className="metric">
              <div className="v">{sweep.n}</div>
              <div className="k">listeners sampled</div>
            </div>
            <div className="metric">
              <div className="v" style={{ color: "var(--danger)" }}>
                B{sweep.modal_drop_beat + 1}
              </div>
              <div className="k">modal drop beat</div>
            </div>
            <div className="metric">
              <div className="v" style={{ color: "var(--ok)" }}>
                {Math.round(sweep.completion_rate * 100)}%
              </div>
              <div className="k">reach the end</div>
            </div>
          </div>

          <div className="sweep-hist">
            {sweep.drop_histogram.map((count, i) => {
              const h = (count / max) * 100;
              const isModal = i === sweep.modal_drop_beat;
              return (
                <div key={i} className="sweep-col" title={`${count} listeners drop at beat ${i + 1}`}>
                  <div className="sweep-count">{count || ""}</div>
                  <div
                    className="sweep-bar"
                    style={{
                      height: `${h}%`,
                      background: isModal ? "var(--danger)" : "var(--ink-2)",
                    }}
                  />
                  <div className="sweep-x">B{i + 1}</div>
                </div>
              );
            })}
          </div>
          <div className="subline" style={{ marginTop: 12 }}>
            Each bar = listeners whose <b>first</b> drop-off is that beat. The
            crowd corroborates the panel's weakest beat — a distribution, not a
            single verdict. <span className="mono muted">(re-run to sample again)</span>
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <button className="ghost" onClick={run} disabled={busy}>
              ↻ Re-sample
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
