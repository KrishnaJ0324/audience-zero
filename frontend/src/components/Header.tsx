import type { ReactNode } from "react";

/** Slim context bar. The wordmark now lives in the sidebar. */
export function Header({ provider, crumbs }: { provider: string; crumbs?: ReactNode }) {
  const isMock = provider === "mock";
  const today = new Date().toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return (
    <header className="header">
      {crumbs}
      <span className="topbar-spacer" />
      <span className="topbar-date">{today}</span>
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
    </header>
  );
}
