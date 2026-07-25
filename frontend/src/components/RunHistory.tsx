import { useEffect, useState } from "react";
import { api } from "../api";
import type { PanelRun } from "../types";

/**
 * Recent runs, newest first. Clicking one re-opens its SSE stream — the event
 * bus replays the full history instantly, so a cached run looks identical to a
 * live one (the SQLite instant-replay guarantee, §2.8/§2.9).
 */
export function RunHistory({
  onReplay,
  refreshKey,
}: {
  onReplay: (runId: string) => void;
  refreshKey: number;
}) {
  const [runs, setRuns] = useState<PanelRun[]>([]);

  useEffect(() => {
    api.listRuns().then(setRuns).catch(() => {});
  }, [refreshKey]);

  if (!runs.length) return null;

  return (
    <div className="card">
      <h2 data-idx="§">Sessions<span className="note">instant replay</span></h2>
      {runs.slice(0, 8).map((r) => (
        <div key={r.id} className="history-item" onClick={() => onReplay(r.id)}>
          <div style={{ minWidth: 0 }}>
            <div
              className="h-title"
              style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {r.episode_title || r.episode_id}
              {r.parent_run_id && (
                <span className="muted mono" style={{ fontSize: 10, marginLeft: 6 }}>
                  (re-run)
                </span>
              )}
            </div>
            <div className="timeline-tag">
              {r.verdict ? r.verdict.headline : r.status}
            </div>
          </div>
          <span className="mono" style={{ color: "var(--danger)", fontSize: 15 }}>
            →
          </span>
        </div>
      ))}
    </div>
  );
}
