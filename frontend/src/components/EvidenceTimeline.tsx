import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import type { EvidenceKind, EvidenceSpan } from "../types";
import type { LiveState } from "../useRun";
import { AudioDisclosure } from "./AudioDisclosure";

/**
 * Kind colours for the light theme. Hue encodes category — warm = a problem
 * (severity descending: rose → orange → amber), green = a win, cyan = a pacing
 * observation, slate = neutral craft note. Every value clears 4.5:1 on both
 * --panel (#fff, where the chips sit) and --paper (#f5f7fa, behind .ev-detail),
 * which the old beige-era palette did not.
 */
const KIND_COLOR: Record<EvidenceKind, string> = {
  boredom: "#b3243c", no_hook: "#c2410c", recap: "#b45309",
  crowded: "#0e7490", trope: "#475569",
  hook: "#0b7a52", payoff: "#15803d",
};
const KIND_LABEL: Record<EvidenceKind, string> = {
  recap: "recap", crowded: "crowded", no_hook: "weak hook", trope: "cliché",
  boredom: "dead air", hook: "strong hook", payoff: "payoff",
};

const NO_PERSONA = "var(--muted-2)";

/**
 * A span is identified by *who* flagged it, so ticks and highlights carry the
 * persona colour (the kind stays legible in the label and chips). Spans nobody
 * owns — panel-wide observations — fall back to neutral grey.
 */
function spanFill(colors: string[]): string {
  if (colors.length === 0) return NO_PERSONA;
  if (colors.length === 1) return colors[0];
  // split the bar into equal hard-stop bands, one per flagging persona
  const stops = colors.flatMap((c, i) => [
    `${c} ${((i / colors.length) * 100).toFixed(2)}%`,
    `${c} ${(((i + 1) / colors.length) * 100).toFixed(2)}%`,
  ]);
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

/**
 * Evidence Timeline — inspect where and why the episode loses listeners.
 * Beat-time ruler + beat markers + evidence ticks, persona filters, issue chips,
 * a transcript that highlights the selected span, and (for audio versions) a
 * waveform with click-to-seek.
 */
export function EvidenceTimeline({
  state,
  audioName,
}: {
  state: LiveState;
  audioName?: string | null;
}) {
  const { beats, evidenceSpans, personas } = state;
  const [personaFilter, setPersonaFilter] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [peaks, setPeaks] = useState<number[]>([]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const duration = beats.length ? beats[beats.length - 1].end_s || 1 : 1;

  // filtering to one persona means *only* what they flagged — panel-wide spans
  // (no persona_ids) belong to "all listeners", not to any single listener
  const spans = useMemo(
    () =>
      personaFilter
        ? evidenceSpans.filter((s) => s.persona_ids.includes(personaFilter))
        : evidenceSpans,
    [evidenceSpans, personaFilter]
  );

  // Resolve a span's flagging personas to their catalog colours. Under a filter
  // the span is narrowed to that persona, so a co-flagged span shows only their
  // colour instead of the whole multi-persona gradient.
  const colorsFor = useMemo(() => {
    const byId = new Map(personas.map((p) => [p.id, p.color]));
    return (s: EvidenceSpan) => {
      const ids = personaFilter
        ? s.persona_ids.filter((id) => id === personaFilter)
        : s.persona_ids;
      return ids.map((id) => byId.get(id)).filter((c): c is string => !!c);
    };
  }, [personas, personaFilter]);

  // waveform (audio versions / produced clips)
  useEffect(() => {
    if (!audioName) { setPeaks([]); return; }
    api.peaks(audioName, 320).then((r) => setPeaks(r.peaks)).catch(() => setPeaks([]));
  }, [audioName]);

  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const w = (cv.width = cv.clientWidth * 2);
    const h = (cv.height = 120);
    ctx.clearRect(0, 0, w, h);
    const mid = h / 2;
    ctx.fillStyle = "#aab4c6";
    if (peaks.length) {
      const bw = w / peaks.length;
      for (let i = 0; i < peaks.length; i++) {
        const ph = Math.max(1, peaks[i] * (h * 0.9));
        ctx.fillRect(i * bw, mid - ph / 2, Math.max(1, bw - 1), ph);
      }
    } else {
      ctx.fillRect(0, mid - 0.5, w, 1); // flat baseline (script versions)
    }
  }, [peaks]);

  const selectSpan = (s: EvidenceSpan) => {
    setSelected(s.id);
    if (audioRef.current && s.start_s != null) audioRef.current.currentTime = s.start_s;
    const el = transcriptRef.current?.querySelector(`[data-beat="${s.beat_index}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  // read from the filtered set so the detail panel can't linger on a span the
  // current filter has hidden
  const selectedSpan = spans.find((s) => s.id === selected) || null;

  if (!beats.length) return null;

  return (
    <div className="card">
      <h2 data-idx="◷">
        Evidence Timeline
        <span className="note">{audioName ? "waveform · click to seek" : "beat-time · transcript"}</span>
      </h2>

      {/* persona filters */}
      <div className="ev-filters">
        <button
          className={`chip ${!personaFilter ? "on" : ""}`}
          onClick={() => setPersonaFilter(null)}
        >
          all listeners
        </button>
        {personas.map((p) => (
          <button
            key={p.id}
            className={`chip ${personaFilter === p.id ? "on" : ""}`}
            style={{ borderColor: personaFilter === p.id ? p.color : undefined }}
            onClick={() => setPersonaFilter(personaFilter === p.id ? null : p.id)}
          >
            <span className="swatch-dot" style={{ background: p.color }} />
            {p.name}
          </button>
        ))}
      </div>

      {/* waveform + ruler */}
      <div className="ev-ruler">
        <canvas ref={canvasRef} className="ev-wave" />
        {/* beat dividers */}
        {beats.map((b) => (
          <div
            key={b.index}
            className="ev-beatmark"
            style={{ left: `${(b.start_s / duration) * 100}%` }}
          >
            <span className="ev-beatlabel">B{b.index + 1}</span>
          </div>
        ))}
        {/* evidence ticks */}
        {spans.map((s) => {
          const left = ((s.start_s ?? 0) / duration) * 100;
          const width = Math.max(0.6, (((s.end_s ?? 0) - (s.start_s ?? 0)) / duration) * 100);
          const who = s.persona_ids
            .map((id) => personas.find((p) => p.id === id)?.name)
            .filter(Boolean);
          return (
            <button
              key={s.id}
              className={`ev-tick ${selected === s.id ? "sel" : ""}`}
              style={{ left: `${left}%`, width: `${width}%`, background: spanFill(colorsFor(s)) }}
              title={`${who.length ? who.join(", ") : "panel"} · ${KIND_LABEL[s.kind]} — “${s.quote}”`}
              onClick={() => selectSpan(s)}
            />
          );
        })}
        {audioName && (
          <audio ref={audioRef} src={api.audioUrl(audioName)} controls className="ev-audio" />
        )}
      </div>
      {audioName && <AudioDisclosure />}

      {/* selected evidence detail */}
      {selectedSpan && (
        <div
          className="ev-detail fade-in"
          style={{ borderLeftColor: colorsFor(selectedSpan)[0] ?? NO_PERSONA }}
        >
          <span className="ev-kind" style={{ color: KIND_COLOR[selectedSpan.kind] }}>
            {KIND_LABEL[selectedSpan.kind]} · beat {selectedSpan.beat_index + 1}
          </span>
          <span className="ev-quote">“{selectedSpan.quote}”</span>
          {selectedSpan.persona_ids.length > 0 && (
            <span className="ev-who">
              flagged by{" "}
              {selectedSpan.persona_ids.map((id, i) => {
                const p = personas.find((x) => x.id === id);
                return (
                  <span key={id}>
                    {i > 0 && ", "}
                    <span className="swatch-dot" style={{ background: p?.color ?? NO_PERSONA }} />
                    {p?.name ?? id}
                  </span>
                );
              })}
            </span>
          )}
        </div>
      )}

      {/* transcript with beat + span highlighting */}
      <div className="ev-transcript" ref={transcriptRef}>
        {beats.map((b) => {
          const beatSpans = spans.filter((s) => s.beat_index === b.index);
          return (
            <div
              key={b.index}
              data-beat={b.index}
              className={`ev-beat ${selectedSpan?.beat_index === b.index ? "active" : ""}`}
            >
              <div className="ev-beat-head">
                <span className="mono">B{b.index + 1}</span>
                <span className="ev-beat-sum">{b.summary}</span>
                <span className="ev-beat-chips">
                  {[...new Set(beatSpans.map((s) => s.kind))].map((k) => (
                    <span key={k} className="ev-chip" style={{ color: KIND_COLOR[k], borderColor: KIND_COLOR[k] }}>
                      {KIND_LABEL[k]}
                    </span>
                  ))}
                </span>
              </div>
              <p className="ev-beat-text">
                {renderHighlighted(b.text, beatSpans, selected, selectSpan, colorsFor)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function renderHighlighted(
  text: string,
  beatSpans: EvidenceSpan[],
  selected: string | null,
  onClick: (s: EvidenceSpan) => void,
  colorsFor: (s: EvidenceSpan) => string[]
) {
  if (!beatSpans.length) return text;
  const ordered = [...beatSpans].sort((a, b) => a.char_start - b.char_start);
  const parts: ReactNode[] = [];
  let cursor = 0;
  ordered.forEach((s, idx) => {
    const cs = Math.max(cursor, s.char_start);
    const ce = Math.min(text.length, s.char_end);
    if (cs > cursor) parts.push(text.slice(cursor, cs));
    if (ce > cs) {
      parts.push(
        <mark
          key={s.id + idx}
          className={`ev-mark ${selected === s.id ? "sel" : ""}`}
          style={{ ["--k" as any]: colorsFor(s)[0] ?? NO_PERSONA }}
          onClick={() => onClick(s)}
        >
          {text.slice(cs, ce)}
        </mark>
      );
      cursor = ce;
    }
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}
