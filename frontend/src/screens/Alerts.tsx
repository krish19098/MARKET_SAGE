import { Card, ErrorNote, Loading, StageBadge } from "../components/ui";
import { useApi } from "../components/useApi";
import { ist, n2 } from "../format";

export function Alerts() {
  const { data, error } = useApi<any[]>("/alerts?limit=200");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="stack">
      <h1>Alert history</h1>
      <p className="muted">The in-app history is the reliable record. Push delivery is best-effort and depends on the device.</p>
      <Card>
        <ul className="list">
          {data.map((a) => (
            <li key={a.id} className="alert-row">
              <div className="row"><StageBadge stage={a.stage} /><strong>{a.title}</strong></div>
              <p>{a.message}</p>
              <p className="muted small">
                Created {ist(a.created_at)} · data cutoff {ist(a.data_cutoff)}
                {a.probability != null && ` · probability ${n2(a.probability * 100)}%`}
                {a.invalidation && ` · invalidation: ${a.invalidation}`}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
