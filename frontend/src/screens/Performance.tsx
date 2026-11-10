import { Card, ErrorNote, KV, Loading } from "../components/ui";
import { useApi } from "../components/useApi";
import { ist, pct, rupees, signedPct } from "../format";

const R = ({ r }: { r: any }) =>
  r?.value == null ? <span className="muted">n/a (n={r?.n ?? 0})</span> : (
    <span>{pct(r.value)} <span className="muted small">n={r.n}{r.ci95 ? ` · 95% CI ${pct(r.ci95[0])}–${pct(r.ci95[1])}` : ""}</span></span>
  );

export function Performance() {
  const { data, error } = useApi<any>("/performance");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const hz = Object.entries(data.by_horizon ?? {});
  return (
    <div className="stack">
      <h1>Performance & accountability</h1>
      <p className="note">Separate scores are shown deliberately; there is no single flattering number. Simulated and counterfactual values are labelled and kept apart from confirmed P&L.</p>
      <div className="grid3">
        <Card title="Ledger"><KV k="Predictions" v={data.counts.predictions} /><KV k="BUY" v={data.counts.buy} /><KV k="Suppressed" v={data.counts.suppressed} />
          <KV k="Integrity" v={data.ledger_integrity.problems.length === 0 ? "✓ hash chain verified" : `⚠ ${data.ledger_integrity.problems.length} problems`} /></Card>
        <Card title="P&L"><KV k={data.pnl.confirmed_user_pnl.label} v={`${rupees(data.pnl.confirmed_user_pnl.value)} (n=${data.pnl.confirmed_user_pnl.n})`} />
          <KV k={data.pnl.paper_pnl.label} v={`${rupees(data.pnl.paper_pnl.value)} (n=${data.pnl.paper_pnl.n})`} /></Card>
        <Card title="Early warnings"><KV k="Resolved" v={data.early_warning.resolved} /><KV k="False-alert rate" v={<R r={data.early_warning.false_alert_rate} />} />
          <KV k="Median lead time" v={data.early_warning.median_lead_time_hours == null ? "n/a" : `${data.early_warning.median_lead_time_hours.toFixed(1)} h`} /></Card>
      </div>
      <Card title="BUY decisions by horizon">
        <div className="table-wrap"><table>
          <thead><tr><th>Horizon</th><th>Direction accuracy</th><th>Mean gross return</th><th>Brier</th><th>Entry filled</th><th>T1 hit</th><th>Stopped</th><th>Stopped then recovered</th><th>AVOID missed upside</th></tr></thead>
          <tbody>{hz.map(([h, v]: any) => (
            <tr key={h}><td>{h}</td><td><R r={v.buy_direction_accuracy} /></td><td>{signedPct(v.buy_mean_return_gross.value)} <span className="muted small">n={v.buy_mean_return_gross.n}</span></td>
              <td>{v.brier.value?.toFixed(3) ?? "n/a"}</td><td><R r={v.entry_fill_rate} /></td><td><R r={v.target1_hit_rate} /></td><td><R r={v.stop_rate} /></td>
              <td><R r={v.stopped_then_recovered} /></td><td>{signedPct(v.avoid_missed_upside_mean)} <span className="muted small">n={v.avoid_count}</span></td></tr>
          ))}</tbody>
        </table></div>
      </Card>
      <div className="grid2">
        <Card title="Calibration (5 sessions, P(T1 first))">
          {data.calibration_5s.n === 0 ? <p className="muted">No calibrated BUY outcomes yet.</p> : (
            <table><thead><tr><th>Bin</th><th>n</th><th>Mean P</th><th>Observed</th></tr></thead>
              <tbody>{data.calibration_5s.bins.map((b: any, i: number) => <tr key={i}><td>{b.bin.join("–")}</td><td>{b.n}</td><td>{pct(b.mean_p)}</td><td>{pct(b.freq)}</td></tr>)}</tbody></table>
          )}
          {data.calibration_5s.ece != null && <p className="small">Expected calibration error: {data.calibration_5s.ece?.toFixed(3)}</p>}
        </Card>
        <Card title="Exit decisions (counterfactual)">
          <p className="small muted">{data.exits_counterfactual.label}</p>
          <KV k="Exits evaluated" v={data.exits_counterfactual.n} />
          <KV k="Potential loss avoided (₹/share, total)" v={data.exits_counterfactual.potential_loss_avoided_per_share_total.toFixed(2)} />
          <KV k="Potential upside missed (₹/share, total)" v={data.exits_counterfactual.potential_upside_missed_per_share_total.toFixed(2)} />
          <KV k="Net vs holding (₹/share, total)" v={data.exits_counterfactual.net_value_added_per_share_total.toFixed(2)} />
        </Card>
      </div>
      <div className="grid2">
        <Card title="By regime & model version (5 sessions)">
          <ul className="small">{Object.entries(data.by_regime_5s).map(([k, v]: any) => <li key={k}>Regime {k}: {signedPct(v.mean_return)} (n={v.n})</li>)}</ul>
          <ul className="small">{Object.entries(data.by_model_version_5s).map(([k, v]: any) => <li key={k}>{k}: {signedPct(v.mean_return)} (n={v.n})</li>)}</ul>
        </Card>
        <Card title="Learning reports">
          <p className="small">Drift: {data.drift.status}{data.drift.live_brier ? ` (live Brier ${data.drift.live_brier.toFixed(3)} vs expected ${data.drift.expected_brier.toFixed(3)})` : ""}</p>
          <p className="small">Lessons by error cause: {Object.entries(data.lessons_by_cause).map(([k, v]) => `${k} ${v}`).join(" · ") || "none yet"}</p>
          <ul className="small">{data.models.map((m: any) => (
            <li key={m.version}><strong>{m.version}</strong> · {m.status}{m.synthetic ? " · SYNTHETIC data" : ""} · {ist(m.created_at)}
              {m.gate?.failed_checks?.length > 0 && <span> · failed: {m.gate.failed_checks.join(", ")}</span>}</li>
          ))}</ul>
        </Card>
      </div>
      <Card title="Examples">
        <div className="grid2">
          <div><h3>Best (5s)</h3><ul className="small">{data.examples.best.map((e: any) => <li key={e.prediction_id}>{e.symbol} {signedPct(e.return_5s)} · {e.outcome} · {ist(e.created_at)}</li>)}</ul></div>
          <div><h3>Worst (5s)</h3><ul className="small">{data.examples.worst.map((e: any) => <li key={e.prediction_id}>{e.symbol} {signedPct(e.return_5s)} · {e.outcome} · {ist(e.created_at)}</li>)}</ul></div>
        </div>
      </Card>
      <Card title="₹500/day aspiration — what it would require">
        <p className="small muted">{data.aspiration.note}</p>
        <table><thead><tr><th>Capital</th><th>Required annual return</th><th>Required daily return</th></tr></thead>
          <tbody>{data.aspiration.requirements.map((r: any) => <tr key={r.capital}><td>{rupees(r.capital)}</td><td>{pct(r.required_annual_return, 0)}</td><td>{pct(r.required_daily_return, 2)}</td></tr>)}</tbody></table>
      </Card>
    </div>
  );
}
