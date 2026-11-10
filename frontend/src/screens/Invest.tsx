import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { post } from "../api";
import { Card, ErrorNote, KV } from "../components/ui";
import { pct, rupees } from "../format";

const PRESETS = [5000, 10000, 20000, 25000, 50000, 100000];

export function Invest() {
  const [capital, setCapital] = useState(20000);
  const [mode, setMode] = useState<"balanced" | "growth">("balanced");
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setRes(await post("/invest", { capital, mode }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const follow = async (pid: string, qty: number) => {
    const r = await post<{ message: string }>(`/paper/follow/${pid}`, { quantity: qty }).catch((e) => ({ message: String(e) }));
    setMsg(r.message);
  };
  return (
    <div className="stack">
      <h1>Invest</h1>
      <Card>
        <form onSubmit={submit} className="invest-form">
          <label>Capital (₹)
            <input type="number" min={100} step="any" value={capital} onChange={(e) => setCapital(Number(e.target.value))} required />
          </label>
          <div className="row wrap">{PRESETS.map((p) => (
            <button type="button" key={p} className={`chip ${p === capital ? "on" : ""}`} onClick={() => setCapital(p)}>{rupees(p)}</button>
          ))}</div>
          <fieldset className="row">
            <legend>Preference</legend>
            <label className="radio"><input type="radio" checked={mode === "balanced"} onChange={() => setMode("balanced")} /> Balanced — diversification, lower volatility, 0.75% risk/trade</label>
            <label className="radio"><input type="radio" checked={mode === "growth"} onChange={() => setMode("growth")} /> Growth — higher expected return and risk, 1% risk/trade</label>
          </fieldset>
          <button type="submit" disabled={busy}>{busy ? "Calculating…" : "Propose allocation"}</button>
        </form>
        <p className="note">Recommendations are advisory. MARKET SAGE never places orders; equities can lose value and stops can fill worse than planned.</p>
      </Card>
      {error != null && <ErrorNote error={error} />}
      {msg && <p className="note">{msg}</p>}
      {res && (
        <>
          <Card title={`Proposed allocation · analysis cutoff ${res.cutoff}`}>
            <div className="grid3">
              <KV k="Invested" v={rupees(res.total_invested)} />
              <KV k="Entry costs (est.)" v={rupees(res.total_entry_costs)} />
              <KV k="Reserve cash" v={rupees(res.reserve_cash)} />
              <KV k="Loss if all stops hit" v={`${rupees(res.portfolio_loss_at_stops)} (${pct(res.portfolio_loss_pct)})`} />
            </div>
            {res.lines.length === 0 && <p className="muted">No position proposed — cash is the recommendation.</p>}
            <div className="table-wrap">
              <table>
                <thead><tr><th>Stock</th><th>Qty</th><th>Amount</th><th>Entry</th><th>Stop</th><th>T1 / T2</th><th>Costs</th><th>Loss at stop</th><th>R:R</th><th>P(T1 first)</th><th>Horizon</th><th></th></tr></thead>
                <tbody>
                  {res.lines.map((l: any) => (
                    <tr key={l.symbol}>
                      <td><Link to={`/analyst/NSE/${l.symbol}`}>{l.symbol}</Link><div className="muted small">{l.sector}</div></td>
                      <td>{l.quantity}</td><td>{rupees(l.amount)}</td><td>{l.entry_price}</td><td>{l.stop}</td>
                      <td>{l.target1} / {l.target2}</td>
                      <td>{rupees(l.entry_costs)}{!l.costs_verified && <span title="unverified charge schedule"> *</span>}</td>
                      <td>{rupees(l.loss_at_stop)}</td><td>{l.reward_risk}</td><td>{pct(l.probability_up, 0)}</td><td>{l.horizon}</td>
                      <td>{l.prediction_id && <button className="ghost small" onClick={() => void follow(l.prediction_id, l.quantity)}>Paper-follow</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {res.lines.map((l: any) => <p key={l.symbol} className="small"><strong>{l.symbol}:</strong> {l.reason}</p>)}
          </Card>
          <Card title="Why other candidates ranked lower">
            <ul className="list small">{res.rejected.slice(0, 30).map((r: any, i: number) => <li key={i}><strong>{r.symbol}</strong>: {r.reason}</li>)}</ul>
          </Card>
          <Card title="Notes"><ul className="small">{res.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul></Card>
        </>
      )}
    </div>
  );
}
