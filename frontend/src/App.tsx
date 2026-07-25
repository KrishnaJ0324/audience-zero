import { useEffect, useState } from "react";
import { api } from "./api";
import { AttentionChart } from "./components/AttentionChart";
import { BeforeAfterPanel } from "./components/BeforeAfterPanel";
import { Header } from "./components/Header";
import { PersonaCards } from "./components/PersonaCards";
import { PopulationSweepPanel } from "./components/PopulationSweepPanel";
import { RunHistory } from "./components/RunHistory";
import { ScenePanel } from "./components/ScenePanel";
import { ScriptInput } from "./components/ScriptInput";
import { VerdictPanel } from "./components/VerdictPanel";
import { useRun } from "./useRun";

export default function App() {
  const { state, connect, loadStatic } = useRun();
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [historyKey, setHistoryKey] = useState(0);

  useEffect(() => {
    api.health().then((h) => setProvider(h.provider)).catch(() => {});
    // deep-link replay: /?run=<id> loads a persisted run as a static view
    const runId = new URLSearchParams(window.location.search).get("run");
    if (runId) {
      (async () => {
        try {
          const [run, personas] = await Promise.all([api.getRun(runId), api.personas()]);
          const ep = await api.getEpisode(run.episode_id).catch(() => null);
          loadStatic(run, ep, personas);
        } catch {
          /* ignore bad deep link */
        }
      })();
    }
  }, [loadStatic]);

  // refresh the history list whenever a run reaches a terminal-ish phase
  useEffect(() => {
    if (["verdict", "complete", "revised"].includes(state.phase)) {
      setHistoryKey((k) => k + 1);
    }
  }, [state.phase]);

  const runScript = async (title: string, text: string) => {
    setErr(null);
    setBusy(true);
    try {
      const ep = await api.createEpisode(title, text);
      const { run_id } = await api.triggerPanel(ep.id);
      connect(run_id);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const runAudio = async (title: string, file: File) => {
    setErr(null);
    setBusy(true);
    try {
      const ep = await api.createEpisodeAudio(title, file);
      const { run_id } = await api.triggerPanel(ep.id);
      connect(run_id);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const fixBeat = async (target: "weakest" | "ending" = "weakest") => {
    if (!state.runId) return;
    setFixing(true);
    try {
      await api.revise(state.runId, target);
      // revision_ready / audio_ready arrive on the same SSE stream
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setTimeout(() => setFixing(false), 400);
    }
  };

  const rerun = async () => {
    if (!state.runId) return;
    setRerunning(true);
    try {
      const res = await api.rerun(state.runId);
      // switch the live stream to the child run so curves redraw, then the
      // before/after payload lands on run_complete.
      connect(res.child_run_id, { keepScores: false });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setTimeout(() => setRerunning(false), 400);
    }
  };

  const hasRun = state.phase !== "idle";
  const scoringNote =
    state.phase === "scoring"
      ? "Six agents evaluating in parallel — curves drawing as reports land…"
      : null;

  return (
    <div className="app">
      <Header provider={state.provider || provider} />

      <div className="grid">
        <div className="stack">
          <ScriptInput onRun={runScript} onRunAudio={runAudio} busy={busy} />
          <RunHistory refreshKey={historyKey} onReplay={(id) => connect(id)} />
          {err && (
            <div className="card">
              <div className="error">⚠ {err}</div>
            </div>
          )}
          {state.error && (
            <div className="card">
              <div className="error">⚠ {state.error}</div>
            </div>
          )}
        </div>

        <div className="stack">
          {!hasRun && (
            <div className="card empty">
              <div>
                <svg width="64" height="64" viewBox="0 0 48 48" fill="none" style={{ marginBottom: 18 }} className="rule-figure">
                  <circle cx="24" cy="24" r="21.5" stroke="currentColor" strokeWidth="1.2" />
                  <circle cx="24" cy="24" r="13.5" stroke="currentColor" strokeWidth="1.2" />
                  <circle cx="24" cy="24" r="3.2" fill="var(--danger)" />
                  <path d="M24 2.5v9M24 36.5v9M2.5 24h9M36.5 24h9" stroke="currentColor" strokeWidth="1.2" />
                </svg>
                <div className="lede">A test audience for serialized audio</div>
                <div className="sub">
                  Paste a script and run the panel. Six contrastive listener
                  personas predict where the episode loses listeners —{" "}
                  <b style={{ color: "var(--ink)" }}>before publish, not after.</b>
                </div>
              </div>
            </div>
          )}

          {hasRun && (
            <div className="card">
              <h2 data-idx="02">
                Attention Curve
                {scoringNote && <span className="note">{scoringNote}</span>}
              </h2>
              <AttentionChart state={state} showAggregate={!!state.verdict} />
            </div>
          )}

          {hasRun && <PersonaCards state={state} />}

          {state.verdict && (
            <VerdictPanel
              state={state}
              onFix={() => fixBeat("weakest")}
              onStrengthenEnding={() => fixBeat("ending")}
              fixing={fixing || state.phase === "revising"}
            />
          )}

          {state.revisedScene && (
            <ScenePanel state={state} onRerun={rerun} rerunning={rerunning} />
          )}

          {state.beforeAfter && <BeforeAfterPanel cmp={state.beforeAfter} />}

          {state.verdict && state.runId && <PopulationSweepPanel runId={state.runId} />}
        </div>
      </div>
    </div>
  );
}
