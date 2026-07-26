import { useEffect, useState } from "react";
import { api } from "../api";
import type { AnalysisRun, EpisodeMeta, Version } from "../types";

/** An episode: its versions + full analysis-run history (the persistent record
 * a producer returns to). Add a new version, or re-open any past run. */
export function EpisodeView({ id, go }: { id: string; go: (to: string) => void }) {
  const [episode, setEpisode] = useState<EpisodeMeta | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.getEpisode(id).then((d) => {
      setEpisode(d.episode); setVersions(d.versions); setRuns(d.runs);
    }).catch(() => {});
  useEffect(() => { load(); }, [id]);

  const addVersionAndRun = async () => {
    if (!text.trim() || !episode) return;
    setBusy(true);
    try {
      const label = `v${versions.length + 1}`;
      const v = await api.addVersion(id, episode.title, text.trim(), label);
      const { run_id } = await api.analyze(v.id);
      go(`/run/${run_id}`);
    } finally { setBusy(false); }
  };

  const label = (vid: string) => versions.find((v) => v.id === vid)?.label ?? "—";

  return (
    <div className="grid">
      <div className="stack">
        <div className="card">
          <h2 data-idx="01">{episode?.title ?? "Episode"}<span className="note">new version</span></h2>
          <label className="field-label">Paste a revised script</label>
          <textarea rows={12} placeholder="A new version of this episode…" value={text}
            onChange={(e) => setText(e.target.value)} />
          <div className="row" style={{ marginTop: 14 }}>
            <button className="primary" onClick={addVersionAndRun} disabled={busy || !text.trim()}>
              {busy ? "Analyzing…" : `▶ Add ${`v${versions.length + 1}`} & analyze`}
            </button>
          </div>
        </div>
        <div className="card">
          <h2 data-idx="§">Versions<span className="note">{versions.length}</span></h2>
          {versions.map((v) => (
            <div key={v.id} className="history-item" style={{ cursor: "default" }}>
              <div>
                <div className="h-title">{v.label}</div>
                <div className="timeline-tag">
                  {v.source_type} · {v.beats.length} beats
                  {v.parent_version_id ? " · derived" : " · original"}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="stack">
        <div className="card">
          <h2 data-idx="◷">Analysis history<span className="note">{runs.length} runs</span></h2>
          {runs.length === 0 && <div className="subline">No analyses yet.</div>}
          {runs.map((r) => (
            <div key={r.id} className="history-item" onClick={() => go(`/run/${r.id}`)}>
              <div>
                <div className="h-title">
                  {label(r.version_id)}
                  {r.parent_run_id && <span className="muted mono" style={{ fontSize: 10, marginLeft: 6 }}>(re-run)</span>}
                </div>
                <div className="timeline-tag">
                  {r.verdict ? r.verdict.headline : r.status}
                  {r.confidence ? ` · ${r.confidence.label} confidence` : ""}
                </div>
              </div>
              <span className="mono" style={{ color: "var(--accent)" }}>→</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
