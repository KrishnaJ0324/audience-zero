import { useEffect, useState } from "react";
import { api } from "../api";
import type { AnalysisRun, EpisodeMeta, Universe, Version } from "../types";

/** Query params a "continue this universe" link from the Universe Matrix can
 * pass through: which universe this pasted script continues, and which
 * version (in a prior episode) it's a direct continuation of. */
function continueParams(): { universe: string; parent: string } {
  const query = window.location.hash.split("?")[1] ?? "";
  const q = new URLSearchParams(query);
  return { universe: q.get("universe") ?? "", parent: q.get("parent") ?? "" };
}

/** An episode: its versions + full analysis-run history (the persistent record
 * a producer returns to). Add a new version, or re-open any past run. */
export function EpisodeView({ id, go }: { id: string; go: (to: string) => void }) {
  const [episode, setEpisode] = useState<EpisodeMeta | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [universes, setUniverses] = useState<Universe[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [openBibleId, setOpenBibleId] = useState<string | null>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const continuing = continueParams();

  const load = () =>
    api.getEpisode(id).then((d) => {
      setEpisode(d.episode); setVersions(d.versions); setRuns(d.runs);
      api.listUniverses(d.episode.project_id).then(setUniverses).catch(() => {});
    }).catch(() => {});
  useEffect(() => { load(); }, [id]);

  const addVersionAndRun = async () => {
    if (!text.trim() || !episode) return;
    setBusy(true);
    try {
      const label = `v${versions.length + 1}`;
      const v = await api.addVersion(
        id, episode.title, text.trim(), label,
        continuing.parent || undefined, continuing.universe || undefined,
      );
      const { run_id } = await api.analyze(v.id);
      go(`/run/${run_id}`);
    } finally { setBusy(false); }
  };

  const generateMemory = async (versionId: string) => {
    setGeneratingId(versionId);
    try { await api.generateMemory(versionId); setOpenBibleId(versionId); await load(); }
    finally { setGeneratingId(null); }
  };

  const universeName = (uid: string) => universes.find((u) => u.id === uid)?.name ?? "";
  const label = (vid: string) => versions.find((v) => v.id === vid)?.label ?? "—";

  return (
    <div className="grid">
      <div className="stack">
        <div className="card">
          <h2 data-idx="01">{episode?.title ?? "Episode"}<span className="note">new version</span></h2>
          {continuing.universe && (
            <div className="subline" style={{ marginBottom: 10 }}>
              Continuing <b>{universeName(continuing.universe) || "a universe"}</b> from a prior episode —
              the pasted script will be tagged and linked automatically.
            </div>
          )}
          {!continuing.universe && versions.length > 0 && (
            <div className="subline" style={{ marginBottom: 10 }}>
              This episode already has a version — adding another one branches a new universe
              from here automatically.
            </div>
          )}
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
            <div key={v.id} className="history-item" style={{ cursor: "default", flexWrap: "wrap" }}>
              <div>
                <div className="h-title">
                  {v.label}
                  {v.universe_id && (
                    <span className="chip" style={{ marginLeft: 8, cursor: "default" }}>
                      ⑂ {universeName(v.universe_id) || "universe"}
                    </span>
                  )}
                </div>
                <div className="timeline-tag">
                  {v.source_type} · {v.beats.length} beats
                  {v.parent_version_id ? " · derived" : " · original"}
                </div>
                <div className="row" style={{ marginTop: 8 }}>
                  {v.memory_md ? (
                    <button className="ghost" onClick={() => setOpenBibleId(openBibleId === v.id ? null : v.id)}>
                      📖 {openBibleId === v.id ? "Hide" : "Show"} story bible
                    </button>
                  ) : (
                    <button className="ghost" onClick={() => generateMemory(v.id)} disabled={generatingId === v.id}>
                      {generatingId === v.id ? "Generating…" : "📖 Generate story bible"}
                    </button>
                  )}
                </div>
                {openBibleId === v.id && v.memory_md && (
                  <pre className="ev-beat-text" style={{ marginTop: 8, maxWidth: 480, whiteSpace: "pre-wrap" }}>
                    {v.memory_md}
                  </pre>
                )}
              </div>
              <button className="ghost" onClick={() => go(`/tree/${id}?version=${v.id}`)}>
                Explore branches →
              </button>
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
