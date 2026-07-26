import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ProjectMatrix, Version } from "../types";
import { GHOST_PREFIX, UniverseGraphCanvas } from "./UniverseGraphCanvas";

/** A tree of Versions branching across episodes (parent_version_id is the
 * edge, episode sequence is the row). Episodes grow linearly by default (the
 * untagged "Main" line); altering an existing episode auto-branches a new
 * universe — no manual tagging step. A solid node is a real version — click
 * it to open that episode, or branch a brand-new universe from it (so one
 * version can fan out into several different next-episode children). A
 * dashed "ghost" node is the one open next-step for a line that hasn't
 * continued yet — click it to grow that SAME line forward. */
export function UniverseMatrixView({ projectId, go }: { projectId: string; go: (to: string) => void }) {
  const [matrix, setMatrix] = useState<ProjectMatrix | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [forkName, setForkName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.getMatrix(projectId).then(setMatrix).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [projectId]);

  const selected = useMemo(() => {
    if (!matrix || !selectedKey) return null;
    if (selectedKey.startsWith(GHOST_PREFIX)) {
      const source = matrix.versions.find((v) => v.id === selectedKey.slice(GHOST_PREFIX.length));
      if (!source) return null;
      const universe = matrix.universes.find((u) => u.id === source.universe_id);
      return { kind: "ghost" as const, source, universeName: universe?.name ?? "the main timeline" };
    }
    const version = matrix.versions.find((v) => v.id === selectedKey);
    if (!version) return null;
    const universe = matrix.universes.find((u) => u.id === version.universe_id);
    const episode = matrix.episodes.find((e) => e.id === version.episode_id);
    return { kind: "filled" as const, version, universeName: universe?.name ?? "Main", episode };
  }, [matrix, selectedKey]);

  if (err) return <div className="card"><div className="error">⚠ {err}</div></div>;
  if (!matrix) return <div className="card"><div className="subline">Loading matrix…</div></div>;

  const { universes, episodes, versions } = matrix;

  const continueSame = async (source: Version, viaScript: boolean) => {
    setBusy(true); setErr(null);
    try {
      if (viaScript) {
        const { episode } = await api.continueUniverse(source.id);
        go(`/episode/${episode.id}?universe=${source.universe_id}&parent=${source.id}`);
      } else {
        await api.continueUniverse(source.id, instruction.trim() || undefined);
        setInstruction(""); await load();
      }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const fork = async (source: Version, viaScript: boolean) => {
    setBusy(true); setErr(null);
    try {
      if (viaScript) {
        const { episode } = await api.continueUniverse(source.id, undefined, undefined, forkName.trim());
        go(`/episode/${episode.id}?universe=${source.universe_id}&parent=${source.id}`);
      } else {
        await api.continueUniverse(source.id, instruction.trim() || undefined, undefined, forkName.trim());
        setInstruction(""); setForkName(""); await load();
      }
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="grid">
      <div className="stack">
        {selected?.kind === "filled" && (
          <>
            <div className="card">
              <h2 data-idx="§">
                {selected.universeName}<span className="note">{selected.episode?.title}</span>
              </h2>
              <div className="subline">{selected.version.label} · {selected.version.beats.length} beats</div>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="primary" onClick={() => go(`/episode/${selected.version.episode_id}`)}>
                  Open episode →
                </button>
              </div>
            </div>
            <div className="card">
              <h2 data-idx="⑂">Branch a new universe from here</h2>
              <label className="field-label">New universe name (optional — auto-named if left blank)</label>
              <input placeholder="e.g. Kael deserts the gate" style={{ width: "100%" }}
                value={forkName} onChange={(e) => setForkName(e.target.value)} />
              <label className="field-label" style={{ marginTop: 10 }}>Free-form instruction (optional)</label>
              <textarea rows={3} placeholder="what happens next in this new universe…"
                value={instruction} onChange={(ev) => setInstruction(ev.target.value)} />
              <div className="row" style={{ marginTop: 10 }}>
                <button className="primary" onClick={() => fork(selected.version, false)} disabled={busy}>
                  {busy ? "…" : "✦ Generate opening scene"}
                </button>
                <button onClick={() => fork(selected.version, true)} disabled={busy}>
                  📝 Paste script instead
                </button>
              </div>
            </div>
          </>
        )}

        {selected?.kind === "ghost" && (
          <div className="card">
            <h2 data-idx="§">{selected.universeName}<span className="note">continue</span></h2>
            <p className="subline">
              Continue <b>{selected.universeName}</b> from {selected.source.label} into the next episode.
            </p>
            <label className="field-label">Free-form instruction (optional)</label>
            <textarea rows={3} placeholder="what happens next…"
              value={instruction} onChange={(ev) => setInstruction(ev.target.value)} />
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={() => continueSame(selected.source, false)} disabled={busy}>
                {busy ? "…" : "✦ Generate opening scene"}
              </button>
              <button onClick={() => continueSame(selected.source, true)} disabled={busy}>
                📝 Paste script instead
              </button>
            </div>
          </div>
        )}

        {!selected && (
          <div className="card">
            <h2 data-idx="§">Episode graph</h2>
            <p className="subline">
              Episodes grow in a straight line by default. Click any node to open its episode, continue
              it forward, or branch a brand-new universe from it. Altering an existing episode (adding
              another version to it) branches automatically — no manual tagging needed.
            </p>
          </div>
        )}
      </div>

      <div className="stack">
        <div className="card">
          <h2 data-idx="⑂">Universe graph<span className="note">
            {universes.length} universe{universes.length === 1 ? "" : "s"} · {episodes.length} episode{episodes.length === 1 ? "" : "s"}
          </span></h2>
          {err && <div className="error">⚠ {err}</div>}
          {episodes.length === 0 && (
            <div className="subline">No episodes yet — add one from the project page.</div>
          )}
          {episodes.length > 0 && (
            <UniverseGraphCanvas
              universes={universes} episodes={episodes} versions={versions}
              selectedKey={selectedKey} onSelect={setSelectedKey}
            />
          )}
        </div>
      </div>
    </div>
  );
}
