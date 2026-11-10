import { useState } from "react";
import { Link } from "react-router-dom";
import { enablePush } from "../api";
import { ActionBadge, Card, DataBadge, ErrorNote, KV, Loading, StageBadge } from "../components/ui";
import { useApi } from "../components/useApi";
import { ist, pct, rupees } from "../format";

export function Home() {
  const { data, error, loading, reload } = useApi<any>("/home");
  const [pushMsg, setPushMsg] = useState<string | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data || loading) return <Loading />;
  const m = data.market;
  return (
    <div className="stack">
      <header className="page-h">
        <h1>Home</h1>
        <div className="row">
          <button className="ghost" onClick={() => void reload()}>Refresh</button>
          <button className="ghost" onClick={async () => setPushMsg(await enablePush().catch((e) => String(e)))}>Enable alerts</button>
        </div>
      </header>
      {pushMsg && <p className="note">{pushMsg}</p>}
      {data.risks.length > 0 && (
        <Card title="Material risks & data notices">
          <ul className="risks">
            {data.risks.map((r: any, i: number) => (
              <li key={i} className={`risk-${r.level}`}><strong>{r.level.toUpperCase()}:</strong> {r.text}</li>
            ))}
          </ul>
        </Card>
      )}
      <div className="grid2">
        <Card title="Market">
          <KV k="Session" v={`${m.phase.replace("_", " ")}${m.trading_day ? "" : " (non-trading day)"}`} />
          <KV k="Regime" v={m.regime} />
          <KV k="Latest analysis cutoff" v={m.latest_cutoff ?? "none yet"} />
          <KV k="Data" v={<DataBadge status={m.data_status} />} />
          <KV k="Live feed" v={m.feed.connected ? `connected · last tick ${ist(m.feed.last_tick_at)}` : m.feed.status} />
          <KV k="As of" v={ist(m.time_ist)} />
        </Card>
        <Card title="Portfolio" actions={<Link to="/trades">My Trades →</Link>}>
          <KV k="Open positions" v={`${data.portfolio.open_positions} (${data.portfolio.actual} actual · ${data.portfolio.paper} paper)`} />
          <KV k="Market value" v={rupees(data.portfolio.market_value)} />
          <KV k="Unrealised P&L" v={rupees(data.portfolio.unrealized_pnl)} />
          <Link to="/invest" className="button">Plan an investment</Link>
        </Card>
      </div>
      <Card title="Best current opportunities" actions={<Link to="/invest">Allocate →</Link>}>
        {data.opportunities.length === 0 ? (
          <p className="muted">No recommendation meets the validated-edge, risk and cost criteria right now. Holding cash is a valid decision.</p>
        ) : (
          <ul className="list">
            {data.opportunities.map((o: any) => (
              <li key={o.prediction_id} className="list-row">
                <Link to={`/analyst/${o.exchange}/${o.symbol}`} className="sym">{o.symbol}</Link>
                <ActionBadge action={o.action} />
                <span>Entry {o.entry_low}–{o.entry_high} · Stop {o.stop} · T1 {o.target1}</span>
                <span className="muted">P(target first) {pct(o.probabilities?.up, 0)} · R:R {o.reward_risk ?? "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Active alerts" actions={<Link to="/alerts">History →</Link>}>
        {data.alerts.length === 0 ? <p className="muted">No alerts.</p> : (
          <ul className="list">
            {data.alerts.map((a: any) => (
              <li key={a.id} className="list-row">
                <StageBadge stage={a.stage} />
                <span><strong>{a.title}</strong></span>
                <span className="muted">{ist(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="muted small">Model: {data.model.note}</p>
    </div>
  );
}
