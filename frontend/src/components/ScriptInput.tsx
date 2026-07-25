import { useEffect, useRef, useState } from "react";
import { api } from "../api";

interface Props {
  onRun: (title: string, text: string) => void;
  onRunAudio: (title: string, file: File) => void;
  busy: boolean;
}

export function ScriptInput({ onRun, onRunAudio, busy }: Props) {
  const [title, setTitle] = useState("Untitled Episode");
  const [text, setText] = useState("");
  const [samples, setSamples] = useState<{ name: string; text: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.scripts().then(setSamples).catch(() => {});
  }, []);

  const loadSample = (s: { name: string; text: string }) => {
    setText(s.text);
    setTitle(prettify(s.name));
  };

  return (
    <div className="card">
      <h2 data-idx="01">Input</h2>
      <label className="field-label">Episode title</label>
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{ marginBottom: 12, fontFamily: "var(--sans)" }}
      />
      <label className="field-label">Paste script</label>
      <textarea
        rows={12}
        placeholder="Paste an episode script… (BEAT / SCENE markers and NAME: dialogue improve segmentation)"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      {samples.length > 0 && (
        <>
          <label className="field-label" style={{ marginTop: 12 }}>
            Load a sample
          </label>
          <div className="row">
            {samples.map((s) => (
              <span key={s.name} className="chip" onClick={() => loadSample(s)}>
                {prettify(s.name)}
              </span>
            ))}
          </div>
        </>
      )}

      <div className="row" style={{ marginTop: 16 }}>
        <button
          className="primary"
          disabled={busy || !text.trim()}
          onClick={() => onRun(title, text)}
        >
          {busy ? "Running panel…" : "▶ Run Panel"}
        </button>
        <button
          className="ghost"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
          title="Audio is a first-class input: STT → beats carry real playback time"
        >
          ⇪ Upload audio
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="audio/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onRunAudio(title === "Untitled Episode" ? f.name : title, f);
          }}
        />
      </div>
    </div>
  );
}

function prettify(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Calib /, "Calibration · ");
}
