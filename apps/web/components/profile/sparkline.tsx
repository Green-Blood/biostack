import type { BodyPoint } from "@/lib/types";

const dayNumber = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86_400_000;

/** A tiny trend line. Decorative: the card carries the numbers; the label says what it shows.
 *  Optional: `band` shades a value range (e.g. the owner's usual 25th–75th percentile) behind the line, and `days`
 *  places points by date over that span (first..last day) so gaps between readings stay visible. Without them the
 *  line is drawn exactly as before (points evenly spaced, scaled to their own range). */
export function Sparkline({ points, label, band, days }: {
  points: BodyPoint[]; label: string; band?: { p25: number; p75: number } | null; days?: [from: string, to: string];
}) {
  const W = 120, H = 32, P = 3;
  const vals = points.map((p) => p.value);
  if (band) vals.push(band.p25, band.p75);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const y = (v: number) => H - P - ((v - lo) / span) * (H - 2 * P);
  const x = (p: BodyPoint, i: number) => {
    if (days) {
      const from = dayNumber(days[0]), width = dayNumber(days[1]) - from || 1;
      return P + ((dayNumber(p.date) - from) / width) * (W - 2 * P);
    }
    return points.length > 1 ? P + (i / (points.length - 1)) * (W - 2 * P) : W / 2;
  };
  const xy = points.map((p, i) => [x(p, i), y(p.value)] as const);
  const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="block h-8 w-full max-w-[160px] overflow-visible">
      {band && (
        <rect x={0} width={W} y={y(band.p75)} height={Math.max(1, y(band.p25) - y(band.p75))} rx={2}
          style={{ fill: "color-mix(in oklab, var(--chart-1) 16%, transparent)" }} />
      )}
      <path d={d} fill="none" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ stroke: "var(--chart-1)" }} />
      <circle cx={lx} cy={ly} r={3} style={{ fill: "var(--chart-1)" }} />
    </svg>
  );
}
