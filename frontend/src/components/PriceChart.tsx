// Lightweight SVG candlestick chart (focused stock view only — never on Home).
type Bar = { t: string; o: number; h: number; l: number; c: number; sma20: number | null; sma50: number | null };

export function PriceChart({ bars, levels }: { bars: Bar[]; levels?: { label: string; value: number | null | undefined }[] }) {
  const data = bars.slice(-120);
  if (!data.length) return null;
  const W = 720, H = 260, pad = 36;
  const lv = (levels ?? []).filter((x) => x.value != null) as { label: string; value: number }[];
  const hi = Math.max(...data.map((b) => b.h), ...lv.map((x) => x.value));
  const lo = Math.min(...data.map((b) => b.l), ...lv.map((x) => x.value));
  const x = (i: number) => pad + (i * (W - 2 * pad)) / data.length;
  const y = (v: number) => pad / 2 + ((hi - v) * (H - pad)) / (hi - lo || 1);
  const bw = Math.max(1, (W - 2 * pad) / data.length - 1);
  const line = (k: "sma20" | "sma50") =>
    data.map((b, i) => (b[k] == null ? "" : `${i === 0 ? "M" : "L"}${x(i) + bw / 2},${y(b[k] as number)}`)).join(" ");
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily price chart with 20 and 50 session moving averages">
        {data.map((b, i) => (
          <g key={b.t}>
            <line x1={x(i) + bw / 2} x2={x(i) + bw / 2} y1={y(b.h)} y2={y(b.l)} className="wick" />
            <rect x={x(i)} width={bw} y={y(Math.max(b.o, b.c))} height={Math.max(1, Math.abs(y(b.o) - y(b.c)))}
              className={b.c >= b.o ? "up" : "down"} />
          </g>
        ))}
        <path d={line("sma20")} className="sma20" fill="none" />
        <path d={line("sma50")} className="sma50" fill="none" />
        {lv.map((l) => (
          <g key={l.label}>
            <line x1={pad} x2={W - pad} y1={y(l.value)} y2={y(l.value)} className={`level level-${l.label.toLowerCase()}`} />
            <text x={W - pad + 2} y={y(l.value) + 4} className="level-label">{l.label}</text>
          </g>
        ))}
        <text x={2} y={y(hi) + 4} className="axis">{hi.toFixed(0)}</text>
        <text x={2} y={y(lo)} className="axis">{lo.toFixed(0)}</text>
      </svg>
      <figcaption className="muted">Last {data.length} sessions · solid: 20-SMA · dashed: 50-SMA · horizontal lines: plan levels</figcaption>
    </figure>
  );
}
