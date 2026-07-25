import { useCallback, useRef, useState } from "react";
import { api } from "./api";
import type {
  Beat,
  BeforeAfter,
  PanelVerdict,
  Persona,
  PersonaReport,
  ProducedAudio,
  RevisedScene,
} from "./types";

export type AgentStatus = "idle" | "thinking" | "done" | "failed";

export interface LiveState {
  runId: string | null;
  phase:
    | "idle"
    | "starting"
    | "scoring"
    | "verdict"
    | "revising"
    | "revised"
    | "complete"
    | "error";
  beats: Beat[];
  personas: Persona[];
  // persona_id -> beat_index -> engagement (fills progressively)
  scores: Record<string, Record<number, number>>;
  agentStatus: Record<string, AgentStatus>;
  reports: Record<string, PersonaReport>;
  verdict: PanelVerdict | null;
  revisedScene: RevisedScene | null;
  producedAudio: ProducedAudio | null;
  beforeAfter: BeforeAfter | null;
  provider: string;
  error: string | null;
}

const initial: LiveState = {
  runId: null,
  phase: "idle",
  beats: [],
  personas: [],
  scores: {},
  agentStatus: {},
  reports: {},
  verdict: null,
  revisedScene: null,
  producedAudio: null,
  beforeAfter: null,
  provider: "",
  error: null,
};

const EVENTS = [
  "run_started",
  "beats_ready",
  "agent_started",
  "beat_scored",
  "agent_done",
  "agent_failed",
  "verdict_ready",
  "revision_started",
  "revision_ready",
  "audio_ready",
  "run_complete",
  "error",
];

export function useRun() {
  const [state, setState] = useState<LiveState>(initial);
  const esRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const connect = useCallback((runId: string, opts?: { keepScores?: boolean }) => {
    close();
    setState((s) => ({
      ...(opts?.keepScores ? s : initial),
      runId,
      phase: "starting",
      beforeAfter: opts?.keepScores ? s.beforeAfter : null,
    }));

    const es = new EventSource(api.eventsUrl(runId));
    esRef.current = es;

    const handle = (type: string, raw: string) => {
      let ev: any = {};
      try {
        ev = JSON.parse(raw);
      } catch {
        return;
      }
      const d = ev.data ?? {};
      setState((s) => {
        const next = { ...s };
        switch (type) {
          case "run_started":
            next.provider = d.provider ?? s.provider;
            next.phase = "starting";
            break;
          case "beats_ready":
            next.beats = d.beats ?? [];
            next.personas = d.personas ?? [];
            next.phase = "scoring";
            next.agentStatus = Object.fromEntries(
              (d.personas ?? []).map((p: Persona) => [p.id, "idle"])
            );
            break;
          case "agent_started":
            next.agentStatus = { ...s.agentStatus, [d.persona_id]: "thinking" };
            break;
          case "beat_scored": {
            const pid = d.persona_id;
            const cur = { ...(s.scores[pid] ?? {}) };
            cur[d.beat_index] = d.engagement;
            next.scores = { ...s.scores, [pid]: cur };
            break;
          }
          case "agent_done":
            next.agentStatus = { ...s.agentStatus, [d.persona_id]: "done" };
            if (d.report) next.reports = { ...s.reports, [d.persona_id]: d.report };
            break;
          case "agent_failed":
            next.agentStatus = { ...s.agentStatus, [d.persona_id]: "failed" };
            break;
          case "verdict_ready":
            next.verdict = d.verdict;
            next.phase = "verdict";
            break;
          case "revision_started":
            next.phase = "revising";
            break;
          case "revision_ready":
            next.revisedScene = d.scene;
            next.phase = "revised";
            break;
          case "audio_ready":
            next.producedAudio = d.produced_audio;
            break;
          case "run_complete":
            if (d.before_after) next.beforeAfter = d.before_after;
            if (s.phase === "scoring" || s.phase === "starting") next.phase = "verdict";
            break;
          case "error":
            next.error = d.error ?? "run failed";
            next.phase = "error";
            break;
        }
        return next;
      });
    };

    EVENTS.forEach((t) =>
      es.addEventListener(t, (e: MessageEvent) => handle(t, e.data))
    );
    es.onerror = () => {
      /* EventSource auto-reconnects; ignore transient blips */
    };
  }, [close]);

  const reset = useCallback(() => {
    close();
    setState(initial);
  }, [close]);

  // fully populate state from persisted objects (deep-link / static replay)
  const loadStatic = useCallback(
    (run: any, episode: any, personas: Persona[]) => {
      close();
      const reports: PersonaReport[] = run.reports ?? [];
      setState({
        ...initial,
        runId: run.id,
        phase: run.produced_audio ? "revised" : "verdict",
        beats: episode?.beats ?? [],
        personas,
        provider: "",
        scores: Object.fromEntries(
          reports.map((r) => [
            r.persona_id,
            Object.fromEntries(r.scores.map((x) => [x.beat_index, x.engagement])),
          ])
        ),
        agentStatus: Object.fromEntries(personas.map((p) => [p.id, "done" as const])),
        reports: Object.fromEntries(reports.map((r) => [r.persona_id, r])),
        verdict: run.verdict,
        revisedScene: run.revised_scene,
        producedAudio: run.produced_audio,
      });
    },
    [close]
  );

  // merge a fetched run (used when loading cached history) into live state
  const hydrate = useCallback((run: any) => {
    setState((s) => ({
      ...s,
      runId: run.id,
      verdict: run.verdict,
      revisedScene: run.revised_scene,
      producedAudio: run.produced_audio,
      reports: Object.fromEntries(
        (run.reports ?? []).map((r: PersonaReport) => [r.persona_id, r])
      ),
      scores: Object.fromEntries(
        (run.reports ?? []).map((r: PersonaReport) => [
          r.persona_id,
          Object.fromEntries(r.scores.map((x) => [x.beat_index, x.engagement])),
        ])
      ),
    }));
  }, []);

  return { state, connect, reset, close, hydrate, loadStatic, setState };
}
