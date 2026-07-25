export function Header({ provider }: { provider: string }) {
  const isMock = provider === "mock";
  const today = new Date().toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return (
    <header className="header">
      <div className="masthead-top">
        <span>Audience Simulator · Cliffhanger Optimizer · Serialized-Audio QA</span>
        <span>{today}</span>
      </div>
      <div className="masthead-main">
        <svg className="brand-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
          {/* concentric "target" = audience zero; a sighting reticle, not an emoji */}
          <circle cx="24" cy="24" r="21.5" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="24" cy="24" r="13.5" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="24" cy="24" r="3.4" fill="var(--danger)" />
          <path d="M24 0v10M24 38v10M0 24h10M38 24h10" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        <div className="masthead-title">
          <h1>Audience Zero</h1>
          <div className="tag">your audience before your audience</div>
        </div>
        <div className="status-pill">
          <span className={`ind ${isMock ? "mock" : ""}`} />
          {provider ? (
            <span>
              engine <b>{provider}</b>
            </span>
          ) : (
            <span>connecting…</span>
          )}
        </div>
      </div>
    </header>
  );
}
