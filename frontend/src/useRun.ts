import { useCallback, useRef, useState } from "react";
import { api } from "./api";
import type {
  AnalysisRun,
  Beat,
  BeforeAfter,
  CalibrationSummary,
  Confidence,
  Diagnostic,
  EvidenceSpan,
  JobState,
  PanelVerdict,
  Persona,
  PersonaReport,
  ProducedAudio,
  RevisionVariant,
  RunManifest,
  Version,
} from "./types";

export type AgentStatus = "idle" | "thinking" | "done" | "failed";
export type Connection = "idle" | "live" | "reconnecting" | "closed";

export interface LiveState {
  runId: string | null;
  phase:
    | "idle" | "starting" | "scoring" | "verdict" | "revising" | "revised"
    | "complete" | "error";
  connection: Connection;
  beats: Beat[];
  personas: Persona[];
  scores: Record<string, Record<number, number>>;
  agentStatus: Record<string, AgentStatus>;
  reports: Record<string, PersonaReport>;
  verdict: PanelVerdict | null;
  confidence: Confidence | null;
  evidenceSpans: EvidenceSpan[];
  diagnostics: Diagnostic[];
  variants: RevisionVariant[];
  job: JobState | null;
  calibration: CalibrationSummary | null;
  manifest: RunManifest | null;
  beforeAfter: BeforeAfter | null;
  producedAudio: ProducedAudio | null;
  provider: string;
  episodeTitle: string;
  versionLabel: string;
  episodeId: string;
  versionId: string;
  projectId: string;
  error: string | null;
}

const initial: LiveState = {
  runId: null, phase: "idle", connection: "idle",
  beats: [], personas: [], scores: {}, agentStatus: {}, reports: {},
  verdict: null, confidence: null, evidenceSpans: [], diagnostics: [], variants: [],
  job: null, calibration: null, manifest: null, beforeAfter: null, producedAudio: null,
  provider: "", episodeTitle: "", versionLabel: "", episodeId: "", versionId: "",
  projectId: "", error: null,
};

const EVENTS = [
  "run_started", "job_state", "beats_ready", "agent_started", "beat_scored",
  "agent_done", "agent_failed", "verdict_ready", "evidence_ready",
  "revision_started", "variant_added", "variant_updated", "revision_ready",
  "audio_ready", "run_complete", "error",
];

export function useRun() {
  const [state, setState] = useState<LiveState>(initial);
  const esRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const connect = useCallback((runId: string, opts?: { keepBefore?: boolean }) => {
    close();
    setState((s) => ({
      ...initial,
      runId,
      phase: "starting",
      connection: "live",
      beforeAfter: opts?.keepBefore ? s.beforeAfter : null,
    }));

    const es = new EventSource(api.eventsUrl(runId));
    esRef.current = es;
    es.onopen = () => setState((s) => ({ ...s, connection: "live" }));
    es.onerror = () =>
      setState((s) => (s.connection === "closed" ? s : { ...s, connection: "reconnecting" }));

    const handle = (type: string, raw: string) => {
      let ev: any = {};
      try { ev = JSON.parse(raw); } catch { return; }
      const d = ev.data ?? {};
      setState((s) => {
        const n = { ...s, connection: "live" as Connection };
        switch (type) {
          case "run_started":
            n.provider = d.provider ?? s.provider;
            n.episodeId = d.episode_id ?? s.episodeId;
            n.versionId = d.version_id ?? s.versionId;
            n.episodeTitle = d.title ?? s.episodeTitle;
            break;
          case "job_state":
            n.job = d.job ?? s.job;
            if (d.job?.status === "failed") n.phase = "error";
            else if (d.job?.stage === "scoring") n.phase = "scoring";
            break;
          case "beats_ready":
            n.beats = d.beats ?? [];
            n.personas = d.personas ?? [];
            n.phase = "scoring";
            n.agentStatus = Object.fromEntries((d.personas ?? []).map((p: Persona) => [p.id, "idle"]));
            break;
          case "agent_started":
            n.agentStatus = { ...s.agentStatus, [d.persona_id]: "thinking" };
            break;
          case "beat_scored": {
            const cur = { ...(s.scores[d.persona_id] ?? {}) };
            cur[d.beat_index] = d.engagement;
            n.scores = { ...s.scores, [d.persona_id]: cur };
            break;
          }
          case "agent_done":
            n.agentStatus = { ...s.agentStatus, [d.persona_id]: "done" };
            if (d.report) n.reports = { ...s.reports, [d.persona_id]: d.report };
            break;
          case "agent_failed":
            n.agentStatus = { ...s.agentStatus, [d.persona_id]: "failed" };
            break;
          case "verdict_ready":
            n.verdict = d.verdict;
            n.confidence = d.confidence ?? s.confidence;
            n.phase = "verdict";
            break;
          case "evidence_ready":
            n.evidenceSpans = d.evidence_spans ?? [];
            n.diagnostics = d.diagnostics ?? [];
            break;
          case "revision_started":
            n.phase = "revising";
            break;
          case "variant_added": {
            const v: RevisionVariant = d.variant;
            n.variants = [...s.variants.filter((x) => x.id !== v.id), v];
            n.producedAudio = v.produced_audio ?? s.producedAudio;
            n.phase = "revised";
            break;
          }
          case "audio_ready":
            n.producedAudio = d.produced_audio ?? s.producedAudio;
            break;
          case "run_complete":
            if (d.before_after) n.beforeAfter = d.before_after;
            if (s.phase === "scoring" || s.phase === "starting") n.phase = "verdict";
            break;
          case "error":
            n.error = d.error ?? "run failed";
            n.phase = "error";
            break;
        }
        return n;
      });
    };

    EVENTS.forEach((t) => es.addEventListener(t, (e: MessageEvent) => handle(t, e.data)));
  }, [close]);

  const reset = useCallback(() => {
    close();
    setState(initial);
  }, [close]);

  /** Populate full state from a persisted run + its version (deep-link/replay). */
  const loadStatic = useCallback((run: AnalysisRun, version: Version | null, personas: Persona[]) => {
    close();
    const reports = run.reports ?? [];
    const acceptedBA =
      (run.revision_variants ?? []).find((v) => v.status === "accepted" && v.before_after)?.before_after ??
      (run.revision_variants ?? []).find((v) => v.before_after)?.before_after ??
      null;
    setState({
      ...initial,
      runId: run.id,
      connection: "closed",
      phase: run.revision_variants?.length ? "revised" : "verdict",
      beats: version?.beats ?? [],
      personas,
      scores: Object.fromEntries(
        reports.map((r) => [r.persona_id, Object.fromEntries(r.scores.map((x) => [x.beat_index, x.engagement]))])
      ),
      agentStatus: Object.fromEntries(personas.map((p) => [p.id, "done" as const])),
      reports: Object.fromEntries(reports.map((r) => [r.persona_id, r])),
      verdict: run.verdict,
      confidence: run.confidence,
      evidenceSpans: run.evidence_spans ?? [],
      diagnostics: run.diagnostics ?? [],
      variants: run.revision_variants ?? [],
      job: run.job,
      calibration: run.calibration_summary,
      manifest: run.run_manifest,
      beforeAfter: acceptedBA,
      producedAudio: run.produced_audio,
      episodeTitle: run.episode_title,
      versionLabel: run.version_label,
      episodeId: run.episode_id,
      versionId: run.version_id,
      projectId: run.project_id,
    });
  }, [close]);

  /** Merge a REST-updated run (diagnostics/variant mutations) into state. */
  const applyRun = useCallback((run: AnalysisRun) => {
    setState((s) => ({
      ...s,
      diagnostics: run.diagnostics ?? s.diagnostics,
      variants: run.revision_variants ?? s.variants,
    }));
  }, []);

  return { state, connect, reset, close, loadStatic, applyRun, setState };
}
