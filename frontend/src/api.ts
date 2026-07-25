import type {
  AnalysisRun,
  BeforeAfter,
  Diagnostic,
  EpisodeMeta,
  PopulationSweep,
  Project,
  Persona,
  Version,
} from "./types";

const BASE = (import.meta as any).env?.VITE_API_BASE ?? "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

const postJson = (path: string, body?: any) =>
  fetch(`${BASE}${path}`, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

export const api = {
  base: BASE,

  health: () => fetch(`${BASE}/health`).then((r) => j<{ provider: string }>(r)),
  personas: () => fetch(`${BASE}/personas`).then((r) => j<Persona[]>(r)),
  scripts: () =>
    fetch(`${BASE}/scripts`).then((r) => j<{ name: string; text: string }[]>(r)),

  // projects
  listProjects: () => fetch(`${BASE}/projects`).then((r) => j<Project[]>(r)),
  createProject: (name: string, description = "") =>
    postJson(`/projects`, { name, description }).then((r) => j<Project>(r)),
  getProject: (id: string) =>
    fetch(`${BASE}/projects/${id}`).then((r) =>
      j<{ project: Project; episodes: EpisodeMeta[] }>(r)
    ),

  // episodes + versions
  createEpisodeInProject: (projectId: string, title: string, text: string, label = "v1") =>
    postJson(`/projects/${projectId}/episodes`, { title, text, label }).then((r) =>
      j<{ episode: EpisodeMeta; version: Version }>(r)
    ),
  createEpisodeAudioInProject: (projectId: string, title: string, file: File) => {
    const fd = new FormData();
    fd.append("title", title);
    fd.append("audio", file);
    return fetch(`${BASE}/projects/${projectId}/episodes`, { method: "POST", body: fd }).then(
      (r) => j<{ episode: EpisodeMeta; version: Version }>(r)
    );
  },
  getEpisode: (id: string) =>
    fetch(`${BASE}/episodes/${id}`).then((r) =>
      j<{ episode: EpisodeMeta; versions: Version[]; runs: AnalysisRun[] }>(r)
    ),
  addVersion: (episodeId: string, title: string, text: string, label = "v", parent?: string) => {
    const q = new URLSearchParams({ label, ...(parent ? { parent } : {}) });
    return postJson(`/episodes/${episodeId}/versions?${q}`, { title, text, label }).then((r) =>
      j<Version>(r)
    );
  },
  getVersion: (id: string) => fetch(`${BASE}/versions/${id}`).then((r) => j<Version>(r)),

  // quick ad-hoc ingest (default workspace)
  createEpisode: (title: string, text: string) =>
    postJson(`/episodes`, { title, text }).then((r) => j<Version>(r)),
  createEpisodeAudio: (title: string, file: File) => {
    const fd = new FormData();
    fd.append("title", title);
    fd.append("audio", file);
    return fetch(`${BASE}/episodes`, { method: "POST", body: fd }).then((r) => j<Version>(r));
  },

  // runs
  analyze: (versionId: string, parent?: string) => {
    const q = parent ? `?parent=${parent}` : "";
    return postJson(`/versions/${versionId}/analyze${q}`).then((r) => j<{ run_id: string }>(r));
  },
  triggerPanel: (versionId: string, parent?: string) => api.analyze(versionId, parent),
  getRun: (id: string) => fetch(`${BASE}/runs/${id}`).then((r) => j<AnalysisRun>(r)),
  listRuns: () => fetch(`${BASE}/runs`).then((r) => j<AnalysisRun[]>(r)),
  retry: (id: string) => postJson(`/runs/${id}/retry`).then((r) => j<{ run_id: string }>(r)),

  // revisions
  revise: (runId: string, target: "weakest" | "ending" = "weakest") =>
    postJson(`/runs/${runId}/revise?target=${target}`).then((r) => j<{ target: string }>(r)),
  variantStatus: (runId: string, variantId: string, status: string, notes = "") =>
    postJson(`/runs/${runId}/variants/${variantId}/status`, { status, notes }).then((r) =>
      j<AnalysisRun>(r)
    ),
  rerun: (runId: string, variant?: string) => {
    const q = variant ? `?variant=${variant}` : "";
    return postJson(`/runs/${runId}/rerun${q}`).then((r) =>
      j<{ child_run_id: string; before_after: BeforeAfter; run: AnalysisRun }>(r)
    );
  },
  sweep: (runId: string, n = 200) =>
    postJson(`/runs/${runId}/sweep?n=${n}`).then((r) => j<PopulationSweep>(r)),

  // diagnostics collaboration
  addComment: (runId: string, diagId: string, author: string, body: string) =>
    postJson(`/runs/${runId}/diagnostics/${diagId}/comment`, { author, body }).then((r) =>
      j<AnalysisRun>(r)
    ),
  assignDiag: (runId: string, diagId: string, assignee: string | null) =>
    postJson(`/runs/${runId}/diagnostics/${diagId}/assign`, { assignee }).then((r) =>
      j<AnalysisRun>(r)
    ),
  diagStatus: (runId: string, diagId: string, status: string) =>
    postJson(`/runs/${runId}/diagnostics/${diagId}/status`, { status }).then((r) =>
      j<AnalysisRun>(r)
    ),

  // share / export
  share: (runId: string) =>
    postJson(`/runs/${runId}/share`).then((r) => j<{ token: string; path: string }>(r)),
  getShared: (token: string) =>
    fetch(`${BASE}/shared/${token}`).then((r) =>
      j<{ read_only: boolean; run: AnalysisRun; summary: string }>(r)
    ),
  summary: (runId: string) =>
    fetch(`${BASE}/runs/${runId}/summary`).then((r) => j<{ summary: string }>(r)),
  reportPdfUrl: (runId: string) => `${BASE}/runs/${runId}/report.pdf`,

  // audio / waveform
  eventsUrl: (runId: string) => `${BASE}/runs/${runId}/events`,
  audioUrl: (name: string) => `${BASE}/audio/${name}`,
  peaks: (name: string, buckets = 400) =>
    fetch(`${BASE}/audio/${name}/peaks?buckets=${buckets}`).then((r) =>
      j<{ peaks: number[] }>(r)
    ),
};

export type Api = typeof api;
