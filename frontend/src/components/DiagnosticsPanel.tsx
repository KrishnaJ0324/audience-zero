import { useState } from "react";
import { api } from "../api";
import type { Diagnostic } from "../types";
import type { LiveState } from "../useRun";

const SEV_COLOR: Record<string, string> = {
  critical: "var(--danger)", major: "var(--warn)", minor: "var(--muted)", info: "var(--ok)",
};

/** Issue chips → resolve / assign / comment. Read-only in shared view. */
export function DiagnosticsPanel({
  state,
  onRun,
  readOnly,
}: {
  state: LiveState;
  onRun: (r: any) => void;
  readOnly?: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const diags = state.diagnostics;
  if (!diags.length) return null;
  const open = diags.filter((d) => d.status === "open").length;

  return (
    <div className="card">
      <h2 data-idx="◆">
        Diagnostics<span className="note">{open} open · {diags.length} total</span>
      </h2>
      <div className="diag-list">
        {diags.map((d) => (
          <DiagRow
            key={d.id}
            d={d}
            runId={state.runId!}
            expanded={openId === d.id}
            personas={state.personas}
            readOnly={readOnly}
            onToggle={() => setOpenId(openId === d.id ? null : d.id)}
            onRun={onRun}
          />
        ))}
      </div>
    </div>
  );
}

function DiagRow({
  d, runId, expanded, personas, readOnly, onToggle, onRun,
}: {
  d: Diagnostic;
  runId: string;
  expanded: boolean;
  personas: LiveState["personas"];
  readOnly?: boolean;
  onToggle: () => void;
  onRun: (r: any) => void;
}) {
  const [comment, setComment] = useState("");
  const [assignee, setAssignee] = useState(d.assignee ?? "");

  const resolved = d.status !== "open";
  return (
    <div className={`diag ${resolved ? "resolved" : ""}`}>
      <div className="diag-head" onClick={onToggle}>
        <span className="diag-sev" style={{ background: SEV_COLOR[d.severity] }} />
        <span className="mono diag-beat">B{d.beat_index + 1}</span>
        <span className="diag-summary">{d.summary}</span>
        <span className="spacer" />
        {d.assignee && <span className="diag-assignee">@{d.assignee}</span>}
        <span className={`diag-status ${d.status}`}>{d.status}</span>
      </div>
      {expanded && (
        <div className="diag-body fade-in">
          <div className="diag-meta">
            <span className="mono">{d.type}</span>
            {d.persona_ids.length > 0 && (
              <span className="muted">
                flagged by {d.persona_ids.map((id) => personas.find((p) => p.id === id)?.name ?? id).join(", ")}
              </span>
            )}
          </div>
          {d.comments.map((c) => (
            <div key={c.id} className="diag-comment">
              <b>{c.author}</b> {c.body}
            </div>
          ))}
          {!readOnly && (
            <>
              <div className="row" style={{ marginTop: 8 }}>
                <input
                  type="text"
                  placeholder="Add a comment…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  style={{ flex: 2, minWidth: 160 }}
                />
                <button
                  className="ghost"
                  disabled={!comment.trim()}
                  onClick={async () => {
                    onRun(await api.addComment(runId, d.id, "producer", comment.trim()));
                    setComment("");
                  }}
                >
                  Comment
                </button>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <input
                  type="text"
                  placeholder="Assign to…"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                  style={{ flex: 1, minWidth: 120 }}
                />
                <button className="ghost" onClick={async () => onRun(await api.assignDiag(runId, d.id, assignee.trim() || null))}>
                  Assign
                </button>
                <button
                  className={resolved ? "ghost" : "primary"}
                  onClick={async () =>
                    onRun(await api.diagStatus(runId, d.id, resolved ? "open" : "resolved"))
                  }
                >
                  {resolved ? "Reopen" : "✓ Resolve"}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
