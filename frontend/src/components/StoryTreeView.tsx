import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { StoryNode } from "../types";
import { StoryGraphCanvas } from "./StoryGraphCanvas";

/** Time-travel branching: jump back to any beat of a trunk Version, type a
 * free-form instruction, and get a new sibling branch — the original chain
 * and every other branch stay untouched. Attention/persona scoring stays a
 * separate, manual action (materialize -> the existing analyze flow). */
export function StoryTreeView({
  episodeId, versionId, go,
}: { episodeId: string; versionId: string; go: (to: string) => void }) {
  const [nodes, setNodes] = useState<StoryNode[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [seeding, setSeeding] = useState(false);
  const [branching, setBranching] = useState(false);
  const [materializing, setMaterializing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false);
    api.getTree(versionId)
      .then((d) => { setNodes(d.nodes); setSelectedId(d.nodes[0]?.id ?? null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));
  }, [versionId]);

  const selected = useMemo(() => nodes.find((n) => n.id === selectedId) ?? null, [nodes, selectedId]);

  const buildTree = async () => {
    setSeeding(true); setError(null);
    try {
      const d = await api.seedTree(versionId);
      setNodes(d.nodes);
      setSelectedId(d.nodes[0]?.id ?? null);
    } catch (e: any) {
      setError(e.message);
    } finally { setSeeding(false); }
  };

  const branch = async () => {
    if (!selected || !instruction.trim()) return;
    setBranching(true); setError(null);
    try {
      const node = await api.branchNode(selected.id, instruction.trim());
      setNodes((ns) => [...ns, node]);
      setSelectedId(node.id);
      setInstruction("");
    } catch (e: any) {
      setError(e.message);
    } finally { setBranching(false); }
  };

  const analyzeBranch = async () => {
    if (!selected) return;
    setMaterializing(true); setError(null);
    try {
      const { version_id } = await api.materializeNode(selected.id);
      const { run_id } = await api.analyze(version_id);
      go(`/run/${run_id}`);
    } catch (e: any) {
      setError(e.message);
      setMaterializing(false);
    }
  };

  return (
    <div className="grid">
      <div className="stack">
        <div className="card">
          <h2 data-idx="⑂">Story tree<span className="note">{nodes.length} nodes</span></h2>
          {error && <div className="error">⚠ {error}</div>}
          {!loaded && <div className="subline">Loading…</div>}
          {loaded && nodes.length === 0 && (
            <>
              <p className="subline">
                No branches yet for this version. Build the tree from its existing
                beats, then branch from any point with free-form text.
              </p>
              <button className="primary" onClick={buildTree} disabled={seeding}>
                {seeding ? "Building…" : "Build story tree"}
              </button>
            </>
          )}
          {nodes.length > 0 && (
            <StoryGraphCanvas nodes={nodes} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </div>
      </div>

      <div className="stack">
        {selected && (
          <>
            <div className="card">
              <h2 data-idx="§">
                {selected.prompt ? "Branch" : selected.label || "Node"}
                <span className="note">beat {selected.beat_index + 1}</span>
              </h2>
              {selected.prompt && <p className="subline"><i>"{selected.prompt}"</i></p>}
              <pre className="ev-beat-text">{selected.text}</pre>

              {selected.consistency_issues.length > 0 && (
                <div className="row" style={{ marginTop: 10, flexDirection: "column", gap: 6 }}>
                  {selected.consistency_issues.map((ci) => (
                    <div key={ci.id} className="error" style={{ fontSize: 12 }}>
                      ⚠ {ci.character ? `${ci.character}: ` : ""}{ci.summary}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(selected.character_states).length > 0 && (
                <div className="row" style={{ marginTop: 14 }}>
                  {Object.values(selected.character_states).map((cs) => (
                    <span key={cs.name} className="chip" title={cs.memory.join(" · ")}>
                      {cs.name}: {cs.emotional_state}
                    </span>
                  ))}
                </div>
              )}

              <div className="row" style={{ marginTop: 14 }}>
                <button onClick={analyzeBranch} disabled={materializing}>
                  {materializing ? "Analyzing…" : "▶ Analyze this branch"}
                </button>
              </div>
            </div>

            <div className="card">
              <h2 data-idx="✎">Narrate what happens next</h2>
              <label className="field-label">Free-form instruction</label>
              <textarea rows={4} placeholder="e.g. Kael abandons the gate and flees into the forest…"
                value={instruction} onChange={(e) => setInstruction(e.target.value)} />
              <div className="row" style={{ marginTop: 12 }}>
                <button className="primary" onClick={branch} disabled={branching || !instruction.trim()}>
                  {branching ? "Branching…" : "Branch from here"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
