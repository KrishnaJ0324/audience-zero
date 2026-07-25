import { useState } from "react";
import { api } from "../api";
import type { RevisionVariant } from "../types";
import type { LiveState } from "../useRun";
import { AudioDisclosure } from "./AudioDisclosure";

/**
 * Revision Lab — compare the original beat against proposed variants,
 * accept/reject, add notes, and re-run the accepted one to see the lift.
 */
export function RevisionLab({
  state,
  onProposeWeakest,
  onProposeEnding,
  proposing,
  onRun,
  readOnly,
}: {
  state: LiveState;
  onProposeWeakest: () => void;
  onProposeEnding: () => void;
  proposing: boolean;
  onRun: (r: any) => void;
  readOnly?: boolean;
}) {
  const variants = state.variants;
  const beats = state.beats;

  return (
    <div className="card">
      <h2 data-idx="✎">
        Revision Lab<span className="note">{variants.length} variant{variants.length === 1 ? "" : "s"}</span>
      </h2>

      {!readOnly && (
        <div className="row" style={{ marginBottom: variants.length ? 18 : 0 }}>
          <button className="danger" onClick={onProposeWeakest} disabled={proposing}>
            {proposing ? "Producing…" : `✦ Propose fix — beat ${(state.verdict?.weakest_beat ?? 0) + 1}`}
          </button>
          <button className="ghost" onClick={onProposeEnding} disabled={proposing}>
            ⤴ Propose stronger ending
          </button>
        </div>
      )}

      {variants.map((v) => {
        const original = beats.find((b) => b.index === v.beat_index)?.text ?? "";
        return (
          <VariantCard
            key={v.id}
            v={v}
            original={original}
            runId={state.runId!}
            readOnly={readOnly}
            onRun={onRun}
          />
        );
      })}
    </div>
  );
}

function VariantCard({
  v, original, runId, readOnly, onRun,
}: {
  v: RevisionVariant;
  original: string;
  runId: string;
  readOnly?: boolean;
  onRun: (r: any) => void;
}) {
  const [notes, setNotes] = useState(v.notes ?? "");
  const [rerunning, setRerunning] = useState(false);
  const ba = v.before_after;

  const setStatus = async (status: string) =>
    onRun(await api.variantStatus(runId, v.id, status, notes));

  const rerun = async () => {
    setRerunning(true);
    try {
      const res = await api.rerun(runId, v.id);
      onRun(res.run);
    } finally {
      setTimeout(() => setRerunning(false), 400);
    }
  };

  return (
    <div className={`variant ${v.status}`}>
      <div className="variant-head">
        <span className={`variant-badge ${v.status}`}>{v.status}</span>
        <span className="mono">beat {v.beat_index + 1} · {v.target}</span>
        <span className="spacer" />
        {ba && (
          <span className="variant-lift" style={{ color: liftColor(ba) }}>
            {v.target === "ending"
              ? `binge ${sign(ba.binge_lift_pct)}${ba.binge_lift_pct.toFixed(0)}pt`
              : `retention ${sign(ba.lift_pct)}${ba.lift_pct.toFixed(0)}pt`}
          </span>
        )}
      </div>

      <div className="variant-compare">
        <div className="variant-col">
          <div className="field-label">Original</div>
          <div className="scene mini">{original}</div>
        </div>
        <div className="variant-col">
          <div className="field-label">Proposed</div>
          <div className="scene mini">{v.new_text}</div>
        </div>
      </div>
      <div className="rationale">↳ {v.change_rationale}</div>

      {v.produced_audio && (
        <div style={{ marginTop: 10 }}>
          <audio controls src={api.audioUrl(v.produced_audio.path)} style={{ width: "100%" }} />
          <div className="disclosure-row">
            <AudioDisclosure disclosure={v.disclosure} />
            {!readOnly && (
              <label className="consent-select">
                voice consent:
                <select
                  value={v.disclosure.voice_consent}
                  onChange={async (e) => onRun(await api.variantConsent(runId, v.id, e.target.value))}
                >
                  <option value="synthetic_no_consent_needed">synthetic — none needed</option>
                  <option value="consented">consent on file</option>
                  <option value="pending">consent pending</option>
                  <option value="unknown">unknown</option>
                </select>
              </label>
            )}
          </div>
        </div>
      )}

      {!readOnly && (
        <>
          <div className="row" style={{ marginTop: 10 }}>
            <input
              type="text"
              placeholder="Notes on this variant…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              style={{ flex: 2, minWidth: 160 }}
            />
            <button
              className={v.status === "accepted" ? "primary" : "ghost"}
              onClick={() => setStatus(v.status === "accepted" ? "proposed" : "accepted")}
            >
              {v.status === "accepted" ? "✓ Accepted" : "Accept"}
            </button>
            <button className="ghost" onClick={() => setStatus("rejected")}>Reject</button>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={rerun} disabled={rerunning}>
              {rerunning ? "Re-running panel…" : "↻ Re-run panel — show the lift"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

const sign = (x: number) => (x >= 0 ? "+" : "");
const liftColor = (ba: { lift_pct: number; binge_lift_pct: number; target: string }) =>
  (ba.target === "ending" ? ba.binge_lift_pct : ba.lift_pct) >= 0 ? "var(--ok)" : "var(--danger)";
