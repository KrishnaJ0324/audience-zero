import { useEffect, useState } from "react";
import { api } from "../api";
import type { EpisodeMeta, Project } from "../types";
import { PersonaPanel } from "./PersonaPanel";
import { ScriptInput } from "./ScriptInput";

/** A project: its episodes + a "new episode" ingest. */
export function ProjectView({ id, go }: { id: string; go: (to: string) => void }) {
  const [project, setProject] = useState<Project | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeMeta[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () =>
    api.getProject(id).then((d) => { setProject(d.project); setEpisodes(d.episodes); }).catch(() => {});
  useEffect(() => { load(); }, [id]);

  const newEpisode = async (title: string, text: string) => {
    setErr(null); setBusy(true);
    try {
      const { episode, version } = await api.createEpisodeInProject(id, title, text);
      const { run_id } = await api.analyze(version.id);
      go(`/run/${run_id}`);
      void episode;
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const newEpisodeAudio = async (title: string, file: File) => {
    setErr(null); setBusy(true);
    try {
      const { version } = await api.createEpisodeAudioInProject(id, title, file);
      const { run_id } = await api.analyze(version.id);
      go(`/run/${run_id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid">
      <div className="stack">
        <ScriptInput onRun={newEpisode} onRunAudio={newEpisodeAudio} busy={busy} heading="New episode" />
        {err && <div className="card"><div className="error">⚠ {err}</div></div>}
      </div>
      <div className="stack">
        <PersonaPanel projectId={id} />
        <div className="card">
          <h2 data-idx="§">
            {project?.name ?? "Project"}
            <span className="note">{episodes.length} episode{episodes.length === 1 ? "" : "s"}</span>
          </h2>
          {episodes.length === 0 && <div className="subline">No episodes yet — paste a script to create the first one.</div>}
          {episodes.map((e) => (
            <div key={e.id} className="history-item" onClick={() => go(`/episode/${e.id}`)}>
              <div>
                <div className="h-title">{e.title}</div>
                <div className="timeline-tag">episode · {e.id}</div>
              </div>
              <span className="mono" style={{ color: "var(--danger)" }}>→</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
