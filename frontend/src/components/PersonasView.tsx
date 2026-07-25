import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Persona, PersonaDraft } from "../types";

type ChatMsg = { role: "user" | "assistant"; content: string };

/** Manage the test-audience roster: the six built-ins plus user-defined
 * personas, created directly or drafted via a multi-turn chat. */
export function PersonasView({ provider }: { provider: string }) {
  const [roster, setRoster] = useState<Persona[]>([]);
  const [name, setName] = useState("");
  const [archetype, setArchetype] = useState("");
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.personas().then(setRoster).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async () => {
    setErr(null); setBusy(true);
    try {
      await api.createPersona({ name, archetype, system_prompt: prompt, model });
      setName(""); setArchetype(""); setPrompt("");
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    await api.deletePersona(id).catch(() => {});
    load();
  };

  const useDraft = (d: PersonaDraft) => {
    setName(d.name);
    setArchetype(d.archetype);
    setPrompt(d.system_prompt);
  };

  const custom = roster.filter((p) => p.custom);
  const built = roster.filter((p) => !p.custom);

  return (
    <div className="grid">
      <div className="stack">
        <div className="card">
          <h2 data-idx="01">New persona</h2>
          <label className="field-label">Name</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Zoya" style={{ marginBottom: 12, fontFamily: "var(--sans)" }} />
          <label className="field-label">Category</label>
          <input type="text" value={archetype} onChange={(e) => setArchetype(e.target.value)}
            placeholder="e.g. Gen-Z speedrunner" style={{ marginBottom: 12, fontFamily: "var(--sans)" }} />
          <label className="field-label">Persona (system prompt)</label>
          <textarea rows={7} value={prompt} onChange={(e) => setPrompt(e.target.value)}
            placeholder="You are …, describe their tastes, patience, what delights them and what makes them skip." />
          <div className="row" style={{ marginTop: 12 }}>
            <label className="field-label" style={{ margin: "8px 8px 0 0" }}>Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)} className="model-select">
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4o">gpt-4o</option>
            </select>
            <span className="spacer" />
            <button className="primary" onClick={save} disabled={busy || !name.trim() || !prompt.trim()}>
              {busy ? "Saving…" : "＋ Save persona"}
            </button>
          </div>
          {err && <div className="error" style={{ marginTop: 10 }}>⚠ {err}</div>}
          <div className="subline" style={{ marginTop: 12 }}>
            {provider === "openai"
              ? "Custom personas score distinctively — the model reads their prompt on every run."
              : "Offline (mock) mode: custom personas use a neutral profile and won't diverge on the graph. Set an OpenAI key so the model reads their prompt."}
          </div>
        </div>

        <PersonaChat onUseDraft={useDraft} provider={provider} />
      </div>

      <div className="stack">
        <div className="card">
          <h2 data-idx="§">Your personas<span className="note">{custom.length} custom</span></h2>
          {custom.length === 0 && <div className="subline">No custom personas yet — create one, or draft with the chat.</div>}
          {custom.map((p) => (
            <div key={p.id} className="persona-row">
              <span className="swatch-dot" style={{ background: p.color, width: 12, height: 12 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="h-title" style={{ fontSize: 14 }}>{p.name}</div>
                <div className="timeline-tag">{p.archetype} · {p.model}</div>
              </div>
              <button className="ghost del-btn" onClick={() => remove(p.id)} title="Delete persona">✕</button>
            </div>
          ))}
        </div>

        <div className="card">
          <h2 data-idx="◆">Built-in panel<span className="note">always on</span></h2>
          {built.map((p) => (
            <div key={p.id} className="persona-row">
              <span className="swatch-dot" style={{ background: p.color, width: 12, height: 12 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="h-title" style={{ fontSize: 14 }}>{p.name}</div>
                <div className="timeline-tag">{p.archetype} · {p.model}</div>
              </div>
              <span className="diag-status">built-in</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PersonaChat({ onUseDraft, provider }: { onUseDraft: (d: PersonaDraft) => void; provider: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<PersonaDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, draft]);

  const send = async () => {
    if (!input.trim()) return;
    const next: ChatMsg[] = [...messages, { role: "user", content: input.trim() }];
    setMessages(next); setInput(""); setBusy(true);
    try {
      const r = await api.personaChat(next);
      setMessages([...next, { role: "assistant", content: r.reply }]);
      setDraft(r.draft);
    } finally { setBusy(false); }
  };

  return (
    <div className="card">
      <h2 data-idx="02">
        Design with chat
        <span className="note">{provider === "openai" ? "generative" : "offline template"}</span>
      </h2>
      <div className="chat-log">
        {messages.length === 0 && (
          <div className="subline">
            Describe the listener you want to test — their tastes, patience, what makes them skip.
            I'll draft a persona you can refine and save.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>{m.content}</div>
        ))}
        <div ref={endRef} />
      </div>

      {draft && draft.name && (
        <div className="chat-draft fade-in">
          <div className="field-label">Draft · {draft.name} {draft.ready && <span style={{ color: "var(--ok)" }}>✓ ready</span>}</div>
          <div className="scene mini">{draft.system_prompt}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={() => onUseDraft(draft)}>Use this draft →</button>
          </div>
        </div>
      )}

      <div className="row" style={{ marginTop: 12 }}>
        <input
          type="text"
          placeholder="e.g. A true-crime superfan who skips anything sentimental…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          style={{ flex: 1, fontFamily: "var(--sans)" }}
        />
        <button className="ghost" onClick={send} disabled={busy || !input.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
