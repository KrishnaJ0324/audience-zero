import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import type { AnalysisRun, EpisodeMeta, Project } from "../types";
import type { Route } from "../useNav";

/** Fired by any view that mutates projects/episodes so the sidebar can refresh. */
export const DATA_CHANGED = "az:data-changed";
export const notifyDataChanged = () => window.dispatchEvent(new Event(DATA_CHANGED));

const isLive = (r: AnalysisRun) => r.status === "pending" || r.status === "running";
const byNewest = (a: { created_at: string }, b: { created_at: string }) =>
  b.created_at.localeCompare(a.created_at);

export function Sidebar({ route, go }: { route: Route; go: (to: string) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false); // mobile drawer

  const loadProjects = useCallback(
    () => api.listProjects().then((p) => setProjects([...p].sort(byNewest))).catch(() => {}),
    []
  );
  const loadRuns = useCallback(
    () => api.listRuns().then((r) => setRuns([...r].sort(byNewest))).catch(() => {}),
    []
  );

  useEffect(() => {
    loadProjects();
    loadRuns();
    const on = () => { loadProjects(); loadRuns(); };
    window.addEventListener(DATA_CHANGED, on);
    return () => window.removeEventListener(DATA_CHANGED, on);
  }, [loadProjects, loadRuns]);

  // keep the session block honest while something is in flight
  const anyLive = runs.some(isLive);
  useEffect(() => {
    if (!anyLive) return;
    const t = setInterval(loadRuns, 4000);
    return () => clearInterval(t);
  }, [anyLive, loadRuns]);

  // refresh sessions whenever the route changes (e.g. a run was just started)
  useEffect(() => { loadRuns(); }, [route, loadRuns]);

  // close the mobile drawer on navigation
  useEffect(() => { setOpen(false); }, [route]);

  const create = async () => {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    try {
      const p = await api.createProject(n);
      setName("");
      await loadProjects();
      go(`/project/${p.id}`);
    } catch {
      /* surfaced by the projects list staying unchanged */
    } finally {
      setBusy(false);
    }
  };

  const live = runs.filter(isLive).slice(0, 3);
  const recent = live.length ? [] : runs.slice(0, 1);
  const sessions = [...live, ...recent];

  const activeProjectId =
    route.view === "project" ? route.id : undefined;

  return (
    <>
      <button
        className="sb-toggle"
        aria-label="Open navigation"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        ☰ Menu
      </button>

      <aside className={`sidebar ${open ? "open" : ""}`}>
        <button className="sb-brand" onClick={() => go("/")} aria-label="Audience Zero — home">
          <BrandMark />
          <span className="sb-brandtext">
            <span className="wordmark">Audience Zero</span>
            <span className="subword">Validate before you publish</span>
          </span>
        </button>

        <div className="sb-scroll">
          <div className="sb-section">
            <button
              className={`sb-item ${route.view === "projects" ? "active" : ""}`}
              onClick={() => go("/")}
            >
              <Ico d="M3 11 12 3l9 8M6 10v10h12V10" />
              <span className="txt">Quick analysis</span>
            </button>
            <button
              className={`sb-item ${route.view === "personas" ? "active" : ""}`}
              onClick={() => go("/personas")}
            >
              <Ico d="M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20a6.5 6.5 0 0 1 13 0M17 8.2a2.8 2.8 0 1 1 0 5.6M18 15.6a5.2 5.2 0 0 1 3.5 4.4" />
              <span className="txt">Personas</span>
            </button>
          </div>

          <div className="sb-section">
            <div className="sb-label">
              <span>Active session</span>
              {live.length > 0 && <span className="mono">{live.length} live</span>}
            </div>
            {sessions.length === 0 ? (
              <div className="sb-empty">Nothing running. Start an analysis to open a session.</div>
            ) : (
              sessions.map((r) => (
                <button
                  key={r.id}
                  className="sb-session"
                  onClick={() => go(`/run/${r.id}`)}
                  title={r.episode_title}
                >
                  <span className="s-top">
                    <span className={`pulse ${r.status === "complete" ? "ok" : r.status === "failed" ? "fail" : ""}`} />
                    {isLive(r) ? r.job?.stage || r.status : r.status}
                  </span>
                  <div className="s-title">{r.episode_title || "Untitled episode"}</div>
                  <div className="s-meta">
                    {r.version_label} · {fmtTime(r.created_at)}
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="sb-section">
            <div className="sb-label">
              <span>Projects</span>
              <span className="mono">{projects.length}</span>
            </div>

            {projects.map((p) => (
              <ProjectRow
                key={p.id}
                project={p}
                active={p.id === activeProjectId}
                go={go}
              />
            ))}

            {projects.length === 0 && (
              <div className="sb-empty">No projects yet — name one below to keep episodes and runs together.</div>
            )}

            <div className="sb-new">
              <input
                type="text"
                placeholder="New project…"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && create()}
              />
              <button
                className="primary sb-add"
                onClick={create}
                disabled={busy || !name.trim()}
                aria-label="Create project"
                title="Create project"
              >
                +
              </button>
            </div>
          </div>
        </div>

        <div className="sb-foot">
          <span>v2</span>
          <span>{projects.length} proj · {runs.length} runs</span>
        </div>
      </aside>

      <div className={`sb-scrim ${open ? "on" : ""}`} onClick={() => setOpen(false)} />
    </>
  );
}

/** One project row; hovering reveals its episodes in a flyout pinned to the row. */
function ProjectRow({
  project,
  active,
  go,
}: {
  project: Project;
  active: boolean;
  go: (to: string) => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeMeta[] | null>(null);

  const openFlyout = () => {
    window.clearTimeout(closeTimer.current);
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    // clamp so a long list never runs off the bottom of the viewport
    const top = Math.min(Math.max(8, r.top - 6), window.innerHeight - 240);
    setPos({ top, left: r.right + 10 });
    if (episodes === null) {
      api
        .getProject(project.id)
        .then((d) => setEpisodes([...d.episodes].sort(byNewest)))
        .catch(() => setEpisodes([]));
    }
  };
  const scheduleClose = () => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setPos(null), 140);
  };

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  // a new episode elsewhere must invalidate this row's cached list
  useEffect(() => {
    const on = () => setEpisodes(null);
    window.addEventListener(DATA_CHANGED, on);
    return () => window.removeEventListener(DATA_CHANGED, on);
  }, []);

  return (
    <>
      <button
        ref={ref}
        className={`sb-item ${active ? "active" : ""}`}
        onClick={() => go(`/project/${project.id}`)}
        onMouseEnter={openFlyout}
        onMouseLeave={scheduleClose}
        onFocus={openFlyout}
        onBlur={scheduleClose}
        title={project.description || project.name}
      >
        <Ico d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
        <span className="txt">{project.name}</span>
        <span className="caret">›</span>
      </button>

      {/* portalled to <body>: the sidebar's backdrop-filter would otherwise
          become the containing block and its scroller would clip the flyout */}
      {pos && createPortal(
        <div
          className="flyout"
          style={{ top: pos.top, left: pos.left }}
          onMouseEnter={() => window.clearTimeout(closeTimer.current)}
          onMouseLeave={scheduleClose}
        >
          <div className="flyout-head">
            <span className="fh-name">{project.name}</span>
            <span className="fh-count">
              {episodes === null ? "…" : `${episodes.length} ep`}
            </span>
          </div>

          {episodes === null && <div className="sb-empty">Loading episodes…</div>}
          {episodes?.length === 0 && (
            <div className="sb-empty">No episodes yet. Open the project to add the first one.</div>
          )}
          {episodes?.map((e) => (
            <button key={e.id} className="sb-item" onClick={() => go(`/episode/${e.id}`)}>
              <Ico d="M4 5h16v14H4zM8 5v14M4 10h4M4 14h4" />
              <span className="txt">{e.title}</span>
              <span className="ep-date">{fmtDate(e.created_at)}</span>
            </button>
          ))}

          <div className="flyout-open">
            <button className="sb-item" onClick={() => go(`/project/${project.id}`)}>
              <Ico d="M5 12h14M13 6l6 6-6 6" />
              <span className="txt">Open project</span>
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

function Ico({ d }: { d: string }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="21" stroke="currentColor" strokeWidth="1.6" opacity="0.45" />
      <circle cx="24" cy="24" r="13" stroke="currentColor" strokeWidth="1.6" opacity="0.75" />
      <circle cx="24" cy="24" r="4" fill="var(--accent)" />
      <path d="M24 1v9M24 38v9M1 24h9M38 24h9" stroke="currentColor" strokeWidth="1.6" opacity="0.6" />
    </svg>
  );
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  return isNaN(+d) ? "" : d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}
function fmtTime(iso: string) {
  const d = new Date(iso);
  return isNaN(+d) ? "" : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
