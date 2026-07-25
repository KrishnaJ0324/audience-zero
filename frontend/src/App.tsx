import { useEffect, useState } from "react";
import { api } from "./api";
import { EpisodeView } from "./components/EpisodeView";
import { Header } from "./components/Header";
import { ProjectView } from "./components/ProjectView";
import { ProjectsView } from "./components/ProjectsView";
import { RunView } from "./components/RunView";
import type { AnalysisRun } from "./types";
import { useNav } from "./useNav";

export default function App() {
  const { route, go } = useNav();
  const [provider, setProvider] = useState("");

  useEffect(() => {
    api.health().then((h) => setProvider(h.provider)).catch(() => {});
  }, []);

  return (
    <div className="app">
      <Header provider={provider} />

      <nav className="crumbs">
        <a className="crumb" onClick={() => go("/")}>⌂ Projects</a>
        {route.view !== "projects" && route.view !== "shared" && (
          <>
            <span className="crumb-sep">›</span>
            <a className="crumb" onClick={() => window.history.back()}>← Back</a>
          </>
        )}
        {route.view === "shared" && (
          <>
            <span className="crumb-sep">›</span>
            <span className="crumb muted">shared report (read-only)</span>
          </>
        )}
      </nav>

      <div className="view">
        {route.view === "projects" && <ProjectsView go={go} />}
        {route.view === "project" && <ProjectView id={route.id} go={go} />}
        {route.view === "episode" && <EpisodeView id={route.id} go={go} />}
        {route.view === "run" && <RunView key={route.id} runId={route.id} autoSweep={route.sweep} />}
        {route.view === "shared" && <SharedView token={route.token} />}
      </div>
    </div>
  );
}

function SharedView({ token }: { token: string }) {
  const [data, setData] = useState<{ run: AnalysisRun; summary: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getShared(token).then(setData).catch((e) => setErr(e.message));
  }, [token]);

  if (err) return <div className="card"><div className="error">⚠ {err}</div></div>;
  if (!data) return <div className="card"><div className="subline">Loading shared report…</div></div>;

  return (
    <div className="stack">
      <div className="shared-banner">
        <b>{data.run.episode_title}</b> — read-only shared report
        <span className="muted"> · anyone with this link can view (but not edit)</span>
      </div>
      {data.summary && <div className="card"><p className="share-summary">{data.summary}</p></div>}
      <RunView key={data.run.id} runId={data.run.id} shared={data} />
    </div>
  );
}
