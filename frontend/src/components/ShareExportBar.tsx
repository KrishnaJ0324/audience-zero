import { useEffect, useState } from "react";
import { api } from "../api";

/** Producer summary + read-only share link + PDF export. */
export function ShareExportBar({ runId, provider }: { runId: string; provider?: string }) {
  const [summary, setSummary] = useState<string>("");
  const [shareUrl, setShareUrl] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [polishing, setPolishing] = useState(false);

  useEffect(() => {
    api.summary(runId).then((r) => setSummary(r.summary)).catch(() => {});
  }, [runId]);

  const polish = async () => {
    setPolishing(true);
    try {
      const r = await api.summary(runId, true);
      setSummary(r.summary);
    } finally {
      setPolishing(false);
    }
  };

  const makeShare = async () => {
    const { path } = await api.share(runId);
    const url = `${window.location.origin}${window.location.pathname}#${path}`;
    setShareUrl(url);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the input still shows the URL */
    }
  };

  return (
    <div className="card share-card">
      <h2 data-idx="⇱">Report<span className="note">summary · share · export</span></h2>
      {summary && <p className="share-summary">{summary}</p>}
      <div className="row" style={{ marginTop: 14 }}>
        <button className="primary" onClick={makeShare}>🔗 Create read-only link</button>
        <a className="btn-link" href={api.reportPdfUrl(runId)} target="_blank" rel="noreferrer">
          ⬇ Download PDF
        </a>
        {provider === "openai" && (
          <button className="ghost" onClick={polish} disabled={polishing} title="Rewrite the summary with the model (uses one API call)">
            {polishing ? "Polishing…" : "✨ Polish with AI"}
          </button>
        )}
      </div>
      {shareUrl && (
        <div className="row" style={{ marginTop: 10 }}>
          <input type="text" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} style={{ flex: 1 }} />
          <span className="muted mono" style={{ alignSelf: "center", fontSize: 11 }}>
            {copied ? "copied ✓" : "read-only"}
          </span>
        </div>
      )}
    </div>
  );
}
