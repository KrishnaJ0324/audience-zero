// ---- content ----
export interface Beat {
  index: number;
  start_s: number;
  end_s: number;
  summary: string;
  text: string;
}

export interface CharacterProfile {
  name: string;
  role: string;
  behavior_notes: string;
}

export interface MemorySpec {
  theme: string;
  characters: CharacterProfile[];
  constraints: string[];
}

export interface Version {
  id: string;
  title: string;
  source_type: "script" | "audio";
  transcript: string;
  duration_s: number | null;
  beats: Beat[];
  project_id: string;
  episode_id: string;
  label: string;
  parent_version_id: string | null;
  universe_id: string;
  memory_spec: MemorySpec | null;
  memory_md: string;
  created_at: string;
}
// alias — the live SSE state still calls the analyzed content "episode"
export type Episode = Version;

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface EpisodeMeta {
  id: string;
  project_id: string;
  title: string;
  sequence: number;
  created_at: string;
}

// ---- universes (parallel timelines across episodes) ----
export interface Universe {
  id: string;
  project_id: string;
  name: string;
  created_at: string;
}

export interface ProjectMatrix {
  universes: Universe[];
  episodes: EpisodeMeta[];
  versions: Version[];
}

// ---- story tree (time-travel branching) ----
export interface CharacterState {
  name: string;
  memory: string[];
  emotional_state: string;
  relationships: Record<string, string>;
}

export interface ConsistencyIssue {
  id: string;
  severity: "info" | "warning" | "critical";
  summary: string;
  conflicting_fact: string;
  character: string;
}

export interface StoryNode {
  id: string;
  root_version_id: string;
  episode_id: string;
  project_id: string;
  parent_node_id: string | null;
  beat_index: number;
  prompt: string;
  text: string;
  summary: string;
  character_states: Record<string, CharacterState>;
  consistency_issues: ConsistencyIssue[];
  label: string;
  created_at: string;
}

// ---- personas ----
export interface Persona {
  id: string;
  name: string;
  archetype: string;
  model: string;
  color: string;
  audience_weight: number;
  custom?: boolean;
  enabled?: boolean;
  system_prompt?: string;
}

export interface PersonaDraft {
  name: string;
  archetype: string;
  system_prompt: string;
  ready: boolean;
}

export interface PersonaChatReply {
  reply: string;
  draft: PersonaDraft;
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

// ---- confidence ----
export interface Confidence {
  overall: number;
  panel_agreement: number;
  mean_persona_confidence: number;
  disagreement_curve: number[];
  label: "low" | "moderate" | "high";
}

// ---- evidence + diagnostics ----
export type EvidenceKind =
  | "recap" | "crowded" | "no_hook" | "trope" | "boredom" | "hook" | "payoff";

export interface EvidenceSpan {
  id: string;
  beat_index: number;
  kind: EvidenceKind;
  start_s: number | null;
  end_s: number | null;
  char_start: number;
  char_end: number;
  quote: string;
  persona_ids: string[];
  source: "heuristic" | "model";
}

export interface Comment {
  id: string;
  author: string;
  body: string;
  created_at: string;
}

export interface Diagnostic {
  id: string;
  beat_index: number;
  type: string;
  severity: "info" | "minor" | "major" | "critical";
  summary: string;
  persona_ids: string[];
  evidence_span_ids: string[];
  status: "open" | "resolved" | "dismissed";
  assignee: string | null;
  comments: Comment[];
}

// ---- revision + audio ----
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

export interface AudioDisclosure {
  ai_generated: boolean;
  voice_consent:
    | "synthetic_no_consent_needed" | "consented" | "pending" | "unknown";
  note: string;
}

export interface RevisionVariant {
  id: string;
  target: "weakest" | "ending" | "custom";
  beat_index: number;
  new_text: string;
  change_rationale: string;
  casting: Record<string, string>;
  produced_audio: ProducedAudio | null;
  before_after: BeforeAfter | null;
  status: "proposed" | "accepted" | "rejected";
  notes: string;
  rerun_id: string | null;
  disclosure: AudioDisclosure;
  created_at: string;
}

// ---- reproducibility + calibration ----
export interface RunManifest {
  run_id: string;
  provider: string;
  models: Record<string, string>;
  persona_ids: string[];
  reveal_delay_s: number;
  seed_signature: string;
  engine_version: string;
  started_at: string;
  finished_at: string | null;
  duration_s: number | null;
  cost_estimate_usd: number | null;
}

export interface CalibrationSummary {
  state: "uncalibrated" | "calibrated";
  has_actual: boolean;
  predicted_retention: number[] | null;
  actual_retention: number[] | null;
  mae: number | null;
  correlation: number | null;
  per_persona_calibration: Record<string, number>;
}

// ---- job ----
export interface JobState {
  status: "queued" | "running" | "failed" | "complete";
  stage: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  error: string | null;
  updated_at: string;
}

// ---- run aggregate ----
export interface AnalysisRun {
  id: string;
  project_id: string;
  episode_id: string;
  version_id: string;
  parent_run_id: string | null;
  created_at: string;
  job: JobState;
  status: "pending" | "running" | "complete" | "failed";
  verdict: PanelVerdict | null;
  confidence: Confidence | null;
  reports: PersonaReport[];
  evidence_spans: EvidenceSpan[];
  diagnostics: Diagnostic[];
  revision_variants: RevisionVariant[];
  run_manifest: RunManifest | null;
  calibration_summary: CalibrationSummary | null;
  revised_scene: RevisedScene | null;
  produced_audio: ProducedAudio | null;
  revision_target: "weakest" | "ending";
  episode_title: string;
  version_label: string;
}
export type PanelRun = AnalysisRun;

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
  | "run_started" | "job_state" | "beats_ready" | "agent_started" | "beat_scored"
  | "agent_done" | "agent_failed" | "verdict_ready" | "evidence_ready"
  | "revision_started" | "variant_added" | "variant_updated" | "revision_ready"
  | "audio_ready" | "run_complete" | "error" | "ping";

export interface BusEvent<T = any> {
  type: EventType;
  run_id: string;
  data: T;
}
