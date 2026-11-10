import type { ReactNode } from "react";

/** Action badge: text + symbol, never colour alone. */
export function ActionBadge({ action }: { action: string }) {
  const sym: Record<string, string> = { BUY: "▲", HOLD: "■", EXIT: "▼", AVOID: "○", PARTIAL_EXIT: "◐" };
  return (
    <span className={`badge action-${action.toLowerCase()}`} aria-label={`Action ${action}`}>
      {sym[action] ?? "•"} {action.replace("_", " ")}
    </span>
  );
}

/** Data provenance/freshness label (live, delayed, eod, stale, synthetic, historical). */
export function DataBadge({ status }: { status?: string | null }) {
  const s = (status ?? "unknown").toLowerCase();
  const label: Record<string, string> = {
    live: "LIVE", delayed: "DELAYED", eod: "END-OF-DAY", stale: "STALE ⚠", synthetic: "SYNTHETIC (test data)",
    historical: "HISTORICAL", unknown: "UNKNOWN",
  };
  return <span className={`badge data-${s}`}>{label[s] ?? s.toUpperCase()}</span>;
}

export function StageBadge({ stage }: { stage: string }) {
  const label: Record<string, string> = {
    early_warning: "EARLY WARNING · not confirmed", approaching: "APPROACHING · not triggered", confirmed: "CONFIRMED", info: "INFO",
  };
  return <span className={`badge stage-${stage}`}>{label[stage] ?? stage}</span>;
}

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-h">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted" role="status">{what}…</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  return <p className="error" role="alert">{error instanceof Error ? error.message : String(error)}</p>;
}

export function KV({ k, v }: { k: ReactNode; v: ReactNode }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}
