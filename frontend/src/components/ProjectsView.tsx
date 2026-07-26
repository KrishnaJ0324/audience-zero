import { useState } from "react";
import { api } from "../api";
import { ScriptInput } from "./ScriptInput";
import { notifyDataChanged } from "./Sidebar";

/**
 * Landing view: quick analysis only.
 * Projects, their episodes and the active session live in the sidebar.
 */
export function ProjectsView({ go }: { go: (to: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const quickRun = async (title: string, text: string) => {
    setErr(null); setBusy(true);
    try {
      const v = await api.createEpisode(title, text); // default workspace
      const { run_id } = await api.analyze(v.id);
      notifyDataChanged();
      go(`/run/${run_id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const quickRunAudio = async (title: string, file: File) => {
    setErr(null); setBusy(true);
    try {
      const v = await api.createEpisodeAudio(title, file);
      const { run_id } = await api.analyze(v.id);
      notifyDataChanged();
      go(`/run/${run_id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="stack home">
      <div className="page-head">
        <h1>Quick analysis</h1>
        <p>
          Paste a script or drop an audio file. A synthetic panel reads it beat by beat and reports
          where attention drops — before a real audience ever sees it.
        </p>
      </div>

      <ScriptInput onRun={quickRun} onRunAudio={quickRunAudio} busy={busy} heading="Quick analysis" />

      {err && <div className="card"><div className="error">⚠ {err}</div></div>}

      <p className="home-hint">
        Want the history kept? Create a project in the sidebar — episodes, versions and runs stay
        grouped there.
      </p>
    </div>
  );
}
