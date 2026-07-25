import { useEffect, useState } from "react";
import { api } from "../api";
import type { Project } from "../types";
import { ScriptInput } from "./ScriptInput";

/** Landing view: quick analyze + projects list + create. */
export function ProjectsView({ go }: { go: (to: string) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.listProjects().then(setProjects).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const p = await api.createProject(name.trim());
      setName("");
      go(`/project/${p.id}`);
    } finally {
      setBusy(false);
    }
  };

  const quickRun = async (title: string, text: string) => {
    setBusy(true);
    try {
      const v = await api.createEpisode(title, text); // default workspace
      const { run_id } = await api.analyze(v.id);
      go(`/run/${run_id}`);
    } finally { setBusy(false); }
  };
  const quickRunAudio = async (title: string, file: File) => {
    setBusy(true);
    try {
      const v = await api.createEpisodeAudio(title, file);
      const { run_id } = await api.analyze(v.id);
      go(`/run/${run_id}`);
    } finally { setBusy(false); }
  };

  return (
    <div className="stack">
      <ScriptInput onRun={quickRun} onRunAudio={quickRunAudio} busy={busy} heading="Quick analysis" />

      <div className="card">
        <h2 data-idx="§">Projects</h2>
        <div className="row">
          <input
            type="text"
            placeholder="New project name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            style={{ flex: 1, fontFamily: "var(--sans)" }}
          />
          <button className="primary" onClick={create} disabled={busy || !name.trim()}>
            + New project
          </button>
        </div>
      </div>

      {projects.length > 0 ? (
        <div className="card">
          <h2 data-idx="§">Your projects</h2>
          {projects.map((p) => (
            <div key={p.id} className="history-item" onClick={() => go(`/project/${p.id}`)}>
              <div>
                <div className="h-title">{p.name}</div>
                <div className="timeline-tag">{p.description || "—"}</div>
              </div>
              <span className="mono" style={{ color: "var(--danger)" }}>→</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="card empty">
          <div>
            <div className="lede">No projects yet</div>
            <div className="sub">Create a project to group your episodes, versions, and analysis runs — and keep the history when you come back.</div>
          </div>
        </div>
      )}
    </div>
  );
}
