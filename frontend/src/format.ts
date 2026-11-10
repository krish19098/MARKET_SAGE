const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export const rupees = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "—" : inr.format(v));
export const n2 = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "—" : num.format(v));
export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits)}%`;
export const signedPct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
/** Server sends IST ISO strings; show them as IST wall-clock. */
export const ist = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) + " IST" : "—";
