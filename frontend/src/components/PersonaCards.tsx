import { api } from "../api";
import type { LiveState } from "../useRun";
import { AudioDisclosure } from "./AudioDisclosure";

function playAudio(name: string | null | undefined) {
  if (!name) return;
  const a = new Audio(api.audioUrl(name));
  a.play().catch(() => {});
}

export function PersonaCards({ state }: { state: LiveState }) {
  const { personas, agentStatus, reports } = state;
  if (!personas.length) return null;

  return (
    <div className="card">
      <h2 data-idx="03">The Panel<span className="note">six listeners · six tastes</span></h2>
      <div className="persona-grid">
        {personas.map((p) => {
          const status = agentStatus[p.id] ?? "idle";
          const report = reports[p.id];
          const live = status === "done" && report;
          return (
            <div
              key={p.id}
              className={`persona ${live ? "live fade-in" : ""} ${
                status === "thinking" ? "thinking" : ""
              }`}
              style={{ ["--pc" as any]: p.color }}
            >
              <div className="name">
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: "50%",
                    background: p.color,
                    display: "inline-block",
                  }}
                />
                {p.name}
              </div>
              <div className="arch">{p.archetype}</div>
              <div className="quote">
                {status === "thinking" && !report
                  ? "listening…"
                  : report?.verdict_text
                  ? `“${report.verdict_text}”`
                  : status === "failed"
                  ? "— (agent dropped; panel continued at N−1)"
                  : "—"}
              </div>
              <div className="foot">
                <span className="model">{p.model}</span>
                {report?.skip_at_beat != null ? (
                  <span className="skip-badge">skips @ B{report.skip_at_beat + 1}</span>
                ) : report ? (
                  <span style={{ color: "var(--ok)" }}>stays to the end</span>
                ) : (
                  <span className="muted">—</span>
                )}
                {report?.verdict_audio_path && (
                  <button
                    className="play-btn"
                    onClick={() => playAudio(report.verdict_audio_path)}
                    title="Hear this verdict in the persona's cast voice"
                  >
                    ▶ voice
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {Object.values(reports).some((r) => r?.verdict_audio_path) && (
        <AudioDisclosure />
      )}
    </div>
  );
}
