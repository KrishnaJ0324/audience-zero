import { api } from "../api";
import type { LiveState } from "../useRun";

export function ScenePanel({
  state,
  onRerun,
  rerunning,
}: {
  state: LiveState;
  onRerun: () => void;
  rerunning: boolean;
}) {
  const scene = state.revisedScene;
  const audio = state.producedAudio;
  if (!scene) return null;

  return (
    <div className="card fade-in">
      <h2 data-idx="05">Revision<span className="note">beat {scene.beat_index + 1} · produced audio</span></h2>
      <div className="scene">{scene.new_text}</div>
      <div className="rationale">↳ {scene.change_rationale}</div>

      {audio && (
        <div style={{ marginTop: 14 }}>
          <div className="field-label">
            Fully produced · {audio.has_music ? "music bed" : "dry"}
            {audio.has_sfx ? " + SFX" : ""} · {Object.keys(audio.casting).length} voices ·{" "}
            {audio.duration_s.toFixed(1)}s
          </div>
          <audio controls src={api.audioUrl(audio.path)} style={{ width: "100%", marginTop: 8 }} />
        </div>
      )}

      <div className="row" style={{ marginTop: 16 }}>
        <button className="primary" onClick={onRerun} disabled={rerunning || !audio}>
          {rerunning ? "Re-running panel…" : "↻ Re-run panel — show the lift"}
        </button>
      </div>
    </div>
  );
}
