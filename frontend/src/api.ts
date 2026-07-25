import type {
  BeforeAfter,
  Episode,
  PanelRun,
  Persona,
  PopulationSweep,
} from "./types";

// In dev, Vite proxies /api -> :8000. Override with VITE_API_BASE for prod.
const BASE = (import.meta as any).env?.VITE_API_BASE ?? "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  base: BASE,

  health: () => fetch(`${BASE}/health`).then((r) => j<{ provider: string }>(r)),

  personas: () => fetch(`${BASE}/personas`).then((r) => j<Persona[]>(r)),

  scripts: () =>
    fetch(`${BASE}/scripts`).then((r) => j<{ name: string; text: string }[]>(r)),

  createEpisode: (title: string, text: string) =>
    fetch(`${BASE}/episodes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, text }),
    }).then((r) => j<Episode>(r)),

  createEpisodeAudio: (title: string, file: File) => {
    const fd = new FormData();
    fd.append("title", title);
    fd.append("audio", file);
    return fetch(`${BASE}/episodes`, { method: "POST", body: fd }).then((r) =>
      j<Episode>(r)
    );
  },

  triggerPanel: (episodeId: string, parent?: string) => {
    const q = parent ? `?parent=${parent}` : "";
    return fetch(`${BASE}/episodes/${episodeId}/panel${q}`, {
      method: "POST",
    }).then((r) => j<{ run_id: string }>(r));
  },

  getRun: (runId: string) =>
    fetch(`${BASE}/runs/${runId}`).then((r) => j<PanelRun>(r)),

  getEpisode: (episodeId: string) =>
    fetch(`${BASE}/episodes/${episodeId}`).then((r) => j<Episode>(r)),

  listRuns: () => fetch(`${BASE}/runs`).then((r) => j<PanelRun[]>(r)),

  revise: (runId: string, target: "weakest" | "ending" = "weakest") =>
    fetch(`${BASE}/runs/${runId}/revise?target=${target}`, { method: "POST" }).then((r) =>
      j<{ status: string; target: string }>(r)
    ),

  sweep: (runId: string, n = 200) =>
    fetch(`${BASE}/runs/${runId}/sweep?n=${n}`, { method: "POST" }).then((r) =>
      j<PopulationSweep>(r)
    ),

  rerun: (runId: string) =>
    fetch(`${BASE}/runs/${runId}/rerun`, { method: "POST" }).then((r) =>
      j<{ child_run_id: string; before_after: BeforeAfter; run: PanelRun }>(r)
    ),

  eventsUrl: (runId: string) => `${BASE}/runs/${runId}/events`,
  audioUrl: (name: string) => `${BASE}/audio/${name}`,
};
