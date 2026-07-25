import { useEffect, useState } from "react";
import { api } from "../api";
import type { AnalysisRun, Persona } from "../types";
import { useRun } from "../useRun";
import { AttentionChart } from "./AttentionChart";
import { BeforeAfterPanel } from "./BeforeAfterPanel";
import { ConfidencePanel } from "./ConfidencePanel";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { EvidenceTimeline } from "./EvidenceTimeline";
import { JobStatus } from "./JobStatus";
import { PersonaCards } from "./PersonaCards";
import { PopulationSweepPanel } from "./PopulationSweepPanel";
import { RevisionLab } from "./RevisionLab";
import { ShareExportBar } from "./ShareExportBar";
import { VerdictPanel } from "./VerdictPanel";

export function RunView({
  runId,
  autoSweep,
  shared,
}: {
  runId: string;
  autoSweep?: boolean;
  shared?: { run: AnalysisRun; summary: string } | null;
}) {
  const { state, connect, loadStatic, applyRun } = useRun();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [proposing, setProposing] = useState(false);
  const readOnly = !!shared;

  useEffect(() => {
    api.personas().then(setPersonas).catch(() => {});
  }, []);

  useEffect(() => {
    if (!personas.length) return;
    let cancelled = false;
    (async () => {
      if (shared) {
        const version = await api.getVersion(shared.run.version_id).catch(() => null);
        if (!cancelled) loadStatic(shared.run, version, personas);
        return;
      }
      const run = await api.getRun(runId).catch(() => null);
      if (cancelled) return;
      if (run && (run.job?.status === "complete" || run.status === "complete")) {
        const version = await api.getVersion(run.version_id).catch(() => null);
        loadStatic(run, version, personas);
      } else {
        connect(runId); // live (or replays history if still in memory)
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, personas.length, shared]);

  const propose = async (target: "weakest" | "ending") => {
    setProposing(true);
    try {
      await api.revise(runId, target); // variant_added arrives on the SSE stream
    } finally {
      setTimeout(() => setProposing(false), 500);
    }
  };

  const degraded = Object.values(state.agentStatus).filter((s) => s === "failed").length;
  const hasVerdict = !!state.verdict;

  return (
    <div className="stack">
      {!readOnly && <JobStatus state={state} onRetry={() => api.retry(runId).then(() => connect(runId))} degraded={degraded} />}

      <div className="card">
        <h2 data-idx="02">
          Attention Curve
          {state.phase === "scoring" && <span className="note">agents scoring — curves drawing…</span>}
        </h2>
        <AttentionChart state={state} showAggregate={hasVerdict} />
      </div>

      {hasVerdict && (
        <div className="two-col">
          <VerdictPanel state={state} showActions={false} />
          <ConfidencePanel confidence={state.confidence} />
        </div>
      )}

      <PersonaCards state={state} />

      {state.evidenceSpans.length > 0 && <EvidenceTimeline state={state} />}

      {state.diagnostics.length > 0 && <DiagnosticsPanel state={state} onRun={applyRun} readOnly={readOnly} />}

      {hasVerdict && (
        <RevisionLab
          state={state}
          onProposeWeakest={() => propose("weakest")}
          onProposeEnding={() => propose("ending")}
          proposing={proposing || state.phase === "revising"}
          onRun={applyRun}
          readOnly={readOnly}
        />
      )}

      {state.beforeAfter && <BeforeAfterPanel cmp={state.beforeAfter} />}

      {hasVerdict && !readOnly && <ShareExportBar runId={runId} />}

      {hasVerdict && !readOnly && <PopulationSweepPanel runId={runId} autoRun={autoSweep} />}
    </div>
  );
}
