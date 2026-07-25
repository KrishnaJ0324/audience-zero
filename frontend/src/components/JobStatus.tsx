import type { Connection, LiveState } from "../useRun";

const STAGE_LABEL: Record<string, string> = {
  scoring: "Six agents scoring in parallel",
  verdict: "Computing the verdict",
  producing: "Producing spoken verdicts",
  done: "Complete",
  "": "Queued",
};

const CONN_LABEL: Record<Connection, string> = {
  idle: "", live: "live", reconnecting: "reconnecting…", closed: "cached",
};

/** Queued / running / failed / complete + reconnect state + retry. */
export function JobStatus({
  state,
  onRetry,
  degraded,
}: {
  state: LiveState;
  onRetry: () => void;
  degraded?: number; // count of personas that fell back to heuristic
}) {
  const job = state.job;
  const status = job?.status ?? (state.phase === "error" ? "failed" : "running");
  const pct = Math.round((job?.progress ?? (status === "complete" ? 1 : 0.1)) * 100);

  return (
    <div className={`jobbar ${status}`}>
      <div className="jobbar-row">
        <span className={`job-pill ${status}`}>{status}</span>
        <span className="job-stage">
          {status === "failed"
            ? job?.error || state.error || "Analysis failed"
            : STAGE_LABEL[job?.stage ?? ""] ?? job?.stage}
        </span>
        <span className="spacer" />
        {state.connection !== "idle" && (
          <span className={`conn ${state.connection}`}>{CONN_LABEL[state.connection]}</span>
        )}
        {status === "failed" && (
          <button className="danger job-retry" onClick={onRetry}>↻ Retry</button>
        )}
      </div>
      {status !== "complete" && status !== "failed" && (
        <div className="job-track">
          <div className="job-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
      {!!degraded && degraded > 0 && (
        <div className="job-fallback">
          ⚠ {degraded} persona{degraded > 1 ? "s" : ""} fell back to the deterministic
          scorer — a model call was slow or off-schema. The panel continued at N−{degraded}.
        </div>
      )}
    </div>
  );
}
