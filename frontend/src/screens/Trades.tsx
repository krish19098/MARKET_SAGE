import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, post } from "../api";
import { ActionBadge, Card, DataBadge, ErrorNote, Loading, StageBadge } from "../components/ui";
import { useApi } from "../components/useApi";
import { ist, rupees } from "../format";

export function Trades() {
  const { data, error, reload } = useApi<any>("/positions");
  const [assess, setAssess] = useState<Record<number, any>>({});
  const [form, setForm] = useState({ symbol: "", quantity: 1, avg_price: 0, stop: "", target1: "", opened_on: "" });
  const [formErr, setFormErr] = useState<unknown>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setFormErr(null);
    try {
      await post("/positions", {
        symbol: form.symbol.trim().toUpperCase(), quantity: Number(form.quantity), avg_price: Number(form.avg_price),
        stop: form.stop ? Number(form.stop) : null, target1: form.target1 ? Number(form.target1) : null,
        opened_on: form.opened_on || null,
      });
      setForm({ symbol: "", quantity: 1, avg_price: 0, stop: "", target1: "", opened_on: "" });
      void reload();
    } catch (err) {
      setFormErr(err);
    }
  };
  const doAssess = async (id: number) => setAssess({ ...assess, [id]: await api(`/positions/${id}/assessment`) });
  const close = async (id: number) => {
    const px = prompt("Actual exit fill price (₹)?");
    if (!px) return;
    await post(`/positions/${id}/close`, { exit_price: Number(px) });
    void reload();
  };
  return (
    <div className="stack">
      <h1>My Trades</h1>
      <Card title="Open positions">
        {data.open.length === 0 ? <p className="muted">No open positions.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Stock</th><th>Type</th><th>Qty</th><th>Entry</th><th>Current</th><th>P&L</th><th>Stop</th><th>T1</th><th>State</th><th></th></tr></thead>
              <tbody>
                {data.open.map((p: any) => (
                  <tr key={p.id}>
                    <td><Link to={`/analyst/${p.exchange}/${p.symbol}`}>{p.symbol}</Link></td>
                    <td><span className={`badge kind-${p.kind}`}>{p.fill_type}</span></td>
                    <td>{p.quantity}</td><td>{p.avg_price}</td>
                    <td>{p.current_price?.toFixed?.(2) ?? "—"} <DataBadge status={p.price_status} /></td>
                    <td className={p.unrealized_pnl >= 0 ? "pos" : "neg"}>{rupees(p.unrealized_pnl)}</td>
                    <td>{p.stop ?? "—"}</td><td>{p.target1 ?? "—"}</td><td>{p.monitor_state.replace("_", " ")}</td>
                    <td className="row">
                      <button className="ghost small" onClick={() => void doAssess(p.id)}>HOLD/EXIT?</button>
                      {p.kind === "actual" && <button className="ghost small" onClick={() => void close(p.id)}>Close</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {Object.entries(assess).map(([id, a]) => (
          <div key={id} className="assess">
            <ActionBadge action={a.action} /> <strong>Position #{id}</strong> — {a.reasons.join("; ")}
            {a.alerts?.slice(0, 3).map((al: any) => <p key={al.id} className="small"><StageBadge stage={al.stage} /> {al.title} · {ist(al.created_at)}</p>)}
          </div>
        ))}
      </Card>
      <Card title="Record an actual position (your real fill)">
        <form onSubmit={add} className="grid3 form">
          <label>Symbol (NSE)<input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} required /></label>
          <label>Quantity<input type="number" min={1} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} required /></label>
          <label>Average price (₹)<input type="number" step="0.05" min={0.05} value={form.avg_price || ""} onChange={(e) => setForm({ ...form, avg_price: Number(e.target.value) })} required /></label>
          <label>Stop (optional)<input type="number" step="0.05" value={form.stop} onChange={(e) => setForm({ ...form, stop: e.target.value })} /></label>
          <label>Target 1 (optional)<input type="number" step="0.05" value={form.target1} onChange={(e) => setForm({ ...form, target1: e.target.value })} /></label>
          <label>Purchase date<input type="date" value={form.opened_on} onChange={(e) => setForm({ ...form, opened_on: e.target.value })} /></label>
          <button type="submit">Add position</button>
        </form>
        {formErr != null && <ErrorNote error={formErr} />}
        <p className="muted small">Actual positions are your confirmed executions. Paper positions are simulated by MARKET SAGE and labelled SIMULATED.</p>
      </Card>
      <Card title="Closed positions">
        <ul className="list small">{data.closed.map((p: any) => (
          <li key={p.id}>{p.symbol} · {p.kind === "actual" ? "ACTUAL" : "SIMULATED"} · {p.quantity} @ {p.avg_price} → {p.exit_price} · closed {ist(p.closed_at)}</li>
        ))}</ul>
      </Card>
    </div>
  );
}
