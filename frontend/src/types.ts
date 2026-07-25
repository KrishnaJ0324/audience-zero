export interface Beat {
  index: number;
  start_s: number;
  end_s: number;
  summary: string;
  text: string;
}

export interface Episode {
  id: string;
  title: string;
  source_type: "script" | "audio";
  transcript: string;
  duration_s: number | null;
  beats: Beat[];
}

export interface Persona {
  id: string;
  name: string;
  archetype: string;
  model: string;
  color: string;
  audience_weight: number;
}

export interface BeatScore {
  beat_index: number;
  engagement: number;
}

export interface PersonaReport {
  persona_id: string;
  scores: BeatScore[];
  skip_at_beat: number | null;
  drop_reason: string;
  verdict_text: string;
  confidence: number;
  verdict_audio_path: string | null;
}

export interface PerPersonaSummary {
  persona_id: string;
  persona_name: string;
  skip_at_beat: number | null;
  mean_engagement: number;
  verdict_text: string;
}

export interface PanelVerdict {
  aggregate_curve: number[];
  weakest_beat: number;
  predicted_drop_pct: number;
  per_persona_summary: PerPersonaSummary[];
  headline: string;
  retention_curve: number[];
  binge_probability: number;
  final_hook_score: number;
}

export interface RevisedScene {
  beat_index: number;
  new_text: string;
  change_rationale: string;
  casting: Record<string, string>;
}

export interface ProducedAudio {
  path: string;
  duration_s: number;
  casting: Record<string, string>;
  has_sfx: boolean;
  has_music: boolean;
}

export interface PanelRun {
  id: string;
  episode_id: string;
  status: "pending" | "running" | "complete" | "failed";
  verdict: PanelVerdict | null;
  reports: PersonaReport[];
  revised_scene: RevisedScene | null;
  produced_audio: ProducedAudio | null;
  parent_run_id: string | null;
  created_at: string;
  episode_title: string;
}

export interface BeforeAfter {
  before_run_id: string;
  after_run_id: string;
  beat_index: number;
  target: "weakest" | "ending";
  before_curve: number[];
  after_curve: number[];
  before_drop_pct: number;
  after_drop_pct: number;
  lift_pct: number;
  before_binge: number;
  after_binge: number;
  binge_lift_pct: number;
}

export interface PopulationSweep {
  episode_id: string;
  n: number;
  n_beats: number;
  drop_histogram: number[];
  completed: number;
  modal_drop_beat: number;
  completion_rate: number;
  per_archetype: Record<string, number>;
}

export type EventType =
  | "run_started"
  | "beats_ready"
  | "agent_started"
  | "beat_scored"
  | "agent_done"
  | "agent_failed"
  | "verdict_ready"
  | "revision_started"
  | "revision_ready"
  | "audio_ready"
  | "run_complete"
  | "error"
  | "ping";

export interface BusEvent<T = any> {
  type: EventType;
  run_id: string;
  data: T;
}
