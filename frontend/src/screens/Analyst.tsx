import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActionBadge, Card, DataBadge, ErrorNote, KV, Loading } from "../components/ui";
import { PriceChart } from "../components/PriceChart";
import { useApi } from "../components/useApi";
import { ist, pct, signedPct } from "../format";

const SECTION_TITLES: Record<string, string> = {
  "1_market_sector_context": "1. Market & sector context", "2_fundamentals_valuation": "2. Fundamentals & valuation",
  "3_technical_structure": "3. Technical structure", "4_volume_liquidity": "4. Volume & liquidity",
  "5_historical_analogues": "5. Historical analogues", "6_bullish_scenario": "6. Bullish scenario",
  "7_bearish_scenario": "7. Bearish scenario", "8_neutral_scenario": "8. Neutral scenario",
  "9_catalysts_events": "9. Catalysts & events", "10_expected_return_and_downside": "10. Expected return range & downside",
  "11_trade_plan": "11. Entry, stop, targets, horizon", "12_what_changes_view": "12. What would change the view",
  "13_why_selected": "13. Why selected / not selected",
};

function Search() {
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const { data } = useApi<any[]>(q.length >= 1 ? `/instruments?q=${encodeURIComponent(q)}` : null);
  const go = (e: FormEvent) => {
    e.preventDefault();
    if (data?.[0]) nav(`/analyst/${data[0].exchange}/${data[0].symbol}`);
  };
  return (
    <form onSubmit={go} className="search">
      <input placeholder="Search symbol or company" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search instruments" />
      {data && q && (
        <ul className="suggest">{data.slice(0, 8).map((i) => (
          <li key={i.id}><Link to={`/analyst/${i.exchange}/${i.symbol}`} onClick={() => setQ("")}>{i.symbol} <span className="muted">{i.name}</span></Link></li>
        ))}</ul>
      )}
    </form>
  );
}

function Section({ title, value }: { title: string; value: any }) {
  if (value == null) return null;
  let body;
  if (Array.isArray(value)) body = <ul>{value.filter(Boolean).map((v, i) => <li key={i}>{String(v)}</li>)}</ul>;
  else if (typeof value === "object")
    body = <dl className="dl">{Object.entries(value).map(([k, v]) => <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{typeof v === "number" ? (Math.abs(v) < 1 && k !== "horizon_sessions" ? signedPct(v) : v) : Array.isArray(v) ? v.join("–") : String(v)}</dd></div>)}</dl>;
  else body = <p>{String(value)}</p>;
  return <details open><summary>{title}</summary>{body}</details>;
}

export function Analyst() {
  const { exchange, symbol } = useParams();
  const { data, error, loading } = useApi<any>(symbol ? `/analyst/${exchange}/${symbol}` : null);
  return (
    <div className="stack">
      <header className="page-h"><h1>Analyst</h1><Search /></header>
      {!symbol && <p className="muted">Search for a stock to see its evidence, scenarios, analogues and trade plan.</p>}
      {error != null && <ErrorNote error={error} />}
      {symbol && (loading || !data) && !error && <Loading what="Analysing" />}
      {data && (
        <>
          <Card title={<>{data.instrument.symbol} <span className="muted">{data.instrument.name}</span></>}
            actions={<div className="row">{data.action && <ActionBadge action={data.action} />}<DataBadge status={data.data_status} /></div>}>
            <p className="muted small">Latest session {data.latest_session}. {data.note}</p>
            {data.reasons?.length > 0 && <ul className="reasons">{data.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>}
            <PriceChart bars={data.chart} levels={[{ label: "Stop", value: data.plan?.stop }, { label: "T1", value: data.plan?.target1 },
              { label: "T2", value: data.plan?.target2 }]} />
            {data.plan && (
              <div className="grid3">
                <KV k="Entry range" v={`${data.plan.entry_low} – ${data.plan.entry_high}`} />
                <KV k="Stop / invalidation" v={data.plan.stop} />
                <KV k="Targets" v={`${data.plan.target1} / ${data.plan.target2}`} />
                <KV k="Reward:risk (T1)" v={data.plan.reward_risk_t1} />
                <KV k="Horizon" v={`${data.plan.horizon_range[0]}–${data.plan.horizon_range[1]} sessions`} />
                <KV k="P(T1 before stop)" v={data.probabilities ? `${pct(data.probabilities.up, 0)} (calibrated OOS)` : `not issued — ${data.calibration_status}`} />
              </div>
            )}
            {data.plan && <p className="small muted">{data.plan.entry_rule} {data.plan.partial_booking} {data.plan.gap_risk_note}</p>}
          </Card>
          {data.thesis?.conflicts?.length > 0 && <Card title="Disagreement between modules"><ul>{data.thesis.conflicts.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul></Card>}
          <Card title="Investment thesis">
            {Object.entries(SECTION_TITLES).map(([k, t]) => <Section key={k} title={t} value={data.thesis?.[k]} />)}
          </Card>
          <div className="grid2">
            <Card title="Evidence (fact · inference · estimate · unknown)">
              <ul className="evidence">{data.evidence?.map((e: any, i: number) => (
                <li key={i}><span className={`badge kind-${e.kind}`}>{e.kind}</span> <span className={`stance-${e.stance}`}>{e.stance === "bullish" ? "▲" : e.stance === "bearish" ? "▼" : "•"} {e.stance}</span> — {e.statement}</li>
              ))}</ul>
            </Card>
            <Card title="Setups & patterns">
              <ul>{data.setups?.map((s: any, i: number) => <li key={i}><strong>{s.name.replace(/_/g, " ")}</strong> · {s.direction} · <em>{s.stage}</em> — {s.detail}</li>)}</ul>
              <ul>{data.patterns?.map((p: any, i: number) => <li key={i}>{p.name.replace(/_/g, " ")} ({p.bias}, {p.confirmed ? "confirmed" : "unconfirmed"})</li>)}</ul>
              {data.structure && <p className="small">Structure: {data.structure.trend}; support {data.structure.support ? `${data.structure.support.low.toFixed(2)}–${data.structure.support.high.toFixed(2)}` : "n/a"}; resistance {data.structure.resistance ? `${data.structure.resistance.low.toFixed(2)}–${data.structure.resistance.high.toFixed(2)}` : "n/a"}</p>}
            </Card>
          </div>
          {data.analogues && (
            <Card title={`Historical analogues · n=${data.analogues.sample_size}`}>
              <p className="small muted">{data.analogues.method}; period {data.analogues.period?.join(" → ")}{data.analogues.regime_matched ? "; regime-matched" : ""}. Similarity is evidence, not a guarantee.</p>
              <div className="table-wrap"><table>
                <thead><tr><th>Horizon</th><th>Median</th><th>P10</th><th>P90</th><th>Win rate</th><th>MFE med.</th><th>MAE med.</th><th>Failure</th></tr></thead>
                <tbody>{Object.entries(data.analogues.by_horizon).map(([h, v]: any) => (
                  <tr key={h}><td>{h} sessions</td><td>{signedPct(v.median)}</td><td>{signedPct(v.p10)}</td><td>{signedPct(v.p90)}</td><td>{pct(v.win_rate, 0)}</td><td>{signedPct(v.mfe_median)}</td><td>{signedPct(v.mae_median)}</td><td>{pct(v.failure_rate, 0)}</td></tr>
                ))}</tbody>
              </table></div>
            </Card>
          )}
          <Card title="Recorded predictions (immutable ledger)">
            <ul className="list small">{data.history.map((h: any) => (
              <li key={h.id}><ActionBadge action={h.action} /> {ist(h.created_at)} · price {h.price_at_prediction?.toFixed(2)} · stop {h.stop ?? "—"} · T1 {h.target1 ?? "—"}</li>
            ))}</ul>
          </Card>
        </>
      )}
    </div>
  );
}
