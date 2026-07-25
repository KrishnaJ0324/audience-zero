import type { LiveState } from "../useRun";
import { BingeGauge } from "./BingeGauge";

export function VerdictPanel({
  state,
  onFix,
  onStrengthenEnding,
  fixing,
}: {
  state: LiveState;
  onFix: () => void;
  onStrengthenEnding: () => void;
  fixing: boolean;
}) {
  const v = state.verdict;
  if (!v) return null;

  const weakestBeat = state.beats[v.weakest_beat];
  const [pre, post] = splitHeadline(v.headline);
  const stays = v.per_persona_summary.filter((p) => p.skip_at_beat == null).length;

  return (
    <div className="card verdict fade-in">
      <h2 data-idx="04">Verdict</h2>
      <div className="verdict-top">
        <div>
          <div className="headline">
            {pre}
            <span className="num">{post}</span>
          </div>
          <div className="subline">
            Aggregate is audience-weighted; every number is computed by the
            deterministic Verdict Engine — no model wrote this.
          </div>
        </div>
        <BingeGauge value={v.binge_probability} />
      </div>

      <div className="metrics">
        <div className="metric">
          <div className="v" style={{ color: "var(--danger)" }}>
            {v.predicted_drop_pct.toFixed(0)}%
          </div>
          <div className="k">predicted drop</div>
        </div>
        <div className="metric">
          <div className="v">B{v.weakest_beat + 1}</div>
          <div className="k">weakest beat</div>
        </div>
        <div className="metric">
          <div className="v">
            {stays}/{v.per_persona_summary.length}
          </div>
          <div className="k">listeners retained</div>
        </div>
        <div className="metric">
          <div className="v">
            {Math.round((v.retention_curve[v.retention_curve.length - 1] ?? 0) * 100)}%
          </div>
          <div className="k">reach the end</div>
        </div>
      </div>

      {weakestBeat && (
        <div style={{ marginTop: 16 }}>
          <div className="field-label">Weakest beat · B{v.weakest_beat + 1}</div>
          <div className="scene" style={{ maxHeight: 120 }}>
            {weakestBeat.text}
          </div>
        </div>
      )}

      <div className="row" style={{ marginTop: 16 }}>
        <button className="danger" onClick={onFix} disabled={fixing}>
          {fixing ? "Rewriting scene + producing audio…" : `✦ Fix beat ${v.weakest_beat + 1}`}
        </button>
        <button className="ghost" onClick={onStrengthenEnding} disabled={fixing} title="Rewrite the final beat to raise Binge Probability">
          ⤴ Strengthen ending
        </button>
      </div>
    </div>
  );
}

function splitHeadline(h: string): [string, string] {
  // "Predicted 55% listener drop at beat 7" -> keep the %/beat emphatic
  const m = h.match(/(\d+%)/);
  if (!m) return [h, ""];
  const i = h.indexOf(m[1]);
  return [h.slice(0, i), h.slice(i)];
}
