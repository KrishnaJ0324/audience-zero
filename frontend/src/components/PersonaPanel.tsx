import { useEffect, useState } from "react";
import { api } from "../api";
import type { Persona } from "../types";

/** Per-project panel selection: toggle which personas run for this project.
 * The selection persists per project (new projects default to all on). */
export function PersonaPanel({ projectId }: { projectId: string }) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.projectPersonas(projectId).then(setPersonas).catch(() => {});
  }, [projectId]);

  const toggle = async (id: string, enabled: boolean) => {
    setErr(null);
    try {
      setPersonas(await api.toggleProjectPersona(projectId, id, enabled));
    } catch (e: any) {
      setErr(e.message?.includes("400") ? "At least one persona must stay enabled." : e.message);
    }
  };

  const enabled = personas.filter((p) => p.enabled !== false).length;
  const custom = personas.filter((p) => p.custom);
  const built = personas.filter((p) => !p.custom);

  const Row = ({ p }: { p: Persona }) => {
    const on = p.enabled !== false;
    return (
      <div className={`persona-row ${on ? "" : "off"}`}>
        <button
          className={`switch ${on ? "on" : ""}`}
          onClick={() => toggle(p.id, !on)}
          title={on ? "In this project's panel — click to exclude" : "Excluded — click to include"}
          aria-pressed={on}
        >
          <span className="switch-knob" />
        </button>
        <span className="swatch-dot" style={{ background: p.color, width: 12, height: 12, opacity: on ? 1 : 0.4 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="h-title" style={{ fontSize: 14 }}>{p.name}</div>
          <div className="timeline-tag">{p.archetype}{p.custom ? " · custom" : ""}</div>
        </div>
      </div>
    );
  };

  if (!personas.length) return null;

  return (
    <div className="card">
      <h2 data-idx="◆">
        Test panel<span className="note">{enabled} of {personas.length} · for this project</span>
      </h2>
      <div className="subline" style={{ marginBottom: 12 }}>
        Only the switched-on personas test episodes in this project. Set it once — it sticks.
      </div>
      {err && <div className="error" style={{ marginBottom: 10 }}>⚠ {err}</div>}
      {custom.length > 0 && (
        <>
          <div className="field-label">Custom</div>
          {custom.map((p) => <Row key={p.id} p={p} />)}
          <div className="field-label" style={{ marginTop: 12 }}>Built-in</div>
        </>
      )}
      {built.map((p) => <Row key={p.id} p={p} />)}
    </div>
  );
}
