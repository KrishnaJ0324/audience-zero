import type {
  AnalysisRun,
  BeforeAfter,
  CalibrationSummary,
  Diagnostic,
  EpisodeMeta,
  PopulationSweep,
  Project,
  ProjectMatrix,
  Persona,
  StoryNode,
  Universe,
  PersonaChatReply,
  Version,
} from "./types";

/**
 * API origin.
 *
 * Dev: unset, so requests go to the same origin at `/api` and vite.config.ts
 * proxies them to the backend (stripping the `/api` prefix).
 *
 * Deployed: set VITE_API_BASE to the backend origin with NO trailing slash and
 * NO `/api` suffix — the backend serves its routes at the root, e.g.
 *   VITE_API_BASE=https://audience-zero.onrender.com
 * Vite inlines this at BUILD time, so it must be set in the build environment;
 * setting it as a runtime variable on a static host has no effect.
 *
 * The trailing slash is stripped defensively: pasting the URL straight from a
 * browser bar gives ".../" and every path here starts with "/", which would
 * otherwise produce a double slash.
 */
const BASE = String((import.meta as any).env?.VITE_API_BASE ?? "/api").replace(/\/+$/, "");

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
  createPersona: (body: { name: string; archetype: string; system_prompt: string; model?: string; color?: string }) =>
    postJson(`/personas`, body).then((r) => j<Persona>(r)),
  deletePersona: (id: string) =>
    fetch(`${BASE}/personas/${id}`, { method: "DELETE" }).then((r) => j<{ deleted: string }>(r)),
  projectPersonas: (projectId: string) =>
    fetch(`${BASE}/projects/${projectId}/personas`).then((r) => j<Persona[]>(r)),
  toggleProjectPersona: (projectId: string, id: string, enabled: boolean) =>
    postJson(`/projects/${projectId}/personas/${id}/toggle`, { enabled }).then((r) => j<Persona[]>(r)),
  personaChat: (messages: { role: string; content: string }[]) =>
    postJson(`/personas/chat`, { messages }).then((r) => j<PersonaChatReply>(r)),
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

  // universes (parallel timelines across episodes)
  listUniverses: (projectId: string) =>
    fetch(`${BASE}/projects/${projectId}/universes`).then((r) => j<Universe[]>(r)),
  getMatrix: (projectId: string) =>
    fetch(`${BASE}/projects/${projectId}/matrix`).then((r) => j<ProjectMatrix>(r)),
  continueUniverse: (
    versionId: string, instruction?: string, targetEpisodeId?: string, newUniverseName?: string,
  ) =>
    postJson(`/versions/${versionId}/continue`, {
      instruction: instruction ?? null, target_episode_id: targetEpisodeId ?? null,
      new_universe_name: newUniverseName ?? null,
    }).then((r) => j<{ episode: EpisodeMeta; version: Version | null; node: StoryNode | null }>(r)),
  generateMemory: (versionId: string) =>
    postJson(`/versions/${versionId}/memory`).then((r) => j<Version>(r)),

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
  addVersion: (
    episodeId: string, title: string, text: string, label = "v",
    parent?: string, universeId?: string,
  ) => {
    const q = new URLSearchParams({
      label, ...(parent ? { parent } : {}), ...(universeId ? { universe_id: universeId } : {}),
    });
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
  variantConsent: (runId: string, variantId: string, consent: string) =>
    postJson(`/runs/${runId}/variants/${variantId}/consent`, { consent }).then((r) =>
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
  summary: (runId: string, enrich = false) =>
    fetch(`${BASE}/runs/${runId}/summary${enrich ? "?enrich=1" : ""}`).then((r) =>
      j<{ summary: string; enriched?: boolean }>(r)
    ),
  reportPdfUrl: (runId: string) => `${BASE}/runs/${runId}/report.pdf`,

  // story tree (time-travel branching)
  seedTree: (versionId: string) =>
    postJson(`/versions/${versionId}/tree/seed`).then((r) => j<{ nodes: StoryNode[] }>(r)),
  getTree: (versionId: string) =>
    fetch(`${BASE}/versions/${versionId}/tree`).then((r) => j<{ nodes: StoryNode[] }>(r)),
  getNode: (nodeId: string) => fetch(`${BASE}/nodes/${nodeId}`).then((r) => j<StoryNode>(r)),
  branchNode: (nodeId: string, instruction: string) =>
    postJson(`/nodes/${nodeId}/branch`, { instruction }).then((r) => j<StoryNode>(r)),
  materializeNode: (nodeId: string) =>
    postJson(`/nodes/${nodeId}/materialize`).then((r) => j<{ version_id: string }>(r)),

  // calibration (prediction vs actual)
  calibrate: (runId: string, retention: number[]) =>
    postJson(`/runs/${runId}/calibrate`, { retention }).then((r) => j<CalibrationSummary>(r)),
  simulateCalibration: (runId: string) =>
    postJson(`/runs/${runId}/calibrate/simulate`).then((r) => j<CalibrationSummary>(r)),

  // audio / waveform
  eventsUrl: (runId: string) => `${BASE}/runs/${runId}/events`,
  audioUrl: (name: string) => `${BASE}/audio/${name}`,
  peaks: (name: string, buckets = 400) =>
    fetch(`${BASE}/audio/${name}/peaks?buckets=${buckets}`).then((r) =>
      j<{ peaks: number[] }>(r)
    ),
};

export type Api = typeof api;
