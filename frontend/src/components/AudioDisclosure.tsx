import type { AudioDisclosure as Disclosure } from "../types";

const CONSENT_LABEL: Record<string, string> = {
  synthetic_no_consent_needed: "synthetic · no consent needed",
  consented: "voice consent on file",
  pending: "consent pending",
  unknown: "consent unknown",
};

/** Shown wherever generated audio plays (AI-audio disclosure + voice-consent). */
export function AudioDisclosure({ disclosure }: { disclosure?: Disclosure | null }) {
  const d = disclosure ?? {
    ai_generated: true,
    voice_consent: "synthetic_no_consent_needed" as const,
    note: "Voices are AI-generated (synthetic — no real person was cloned).",
  };
  const warn = d.voice_consent === "pending" || d.voice_consent === "unknown";
  return (
    <div className={`disclosure ${warn ? "warn" : ""}`} title={d.note}>
      <span className="disc-dot" aria-hidden="true" />
      <span>AI-generated audio</span>
      <span className="disc-sep">·</span>
      <span>{CONSENT_LABEL[d.voice_consent]}</span>
    </div>
  );
}
