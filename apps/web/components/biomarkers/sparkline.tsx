/** The shape of a marker's history; the last point is marked. Decorative: the numbers are in the text beside it. */
export function Sparkline({ values, out = false, width = 72, height = 26 }: { values: number[]; out?: boolean; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 8) + 3, height - 4 - ((v - lo) / span) * (height - 8)] as const);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className={out ? "text-outrange" : "text-data"}>
      <polyline points={`${pts[0][0]},${height} ${line} ${lx},${height}`} fill="currentColor" fillOpacity="0.1" stroke="none" />
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r="2.5" fill="currentColor" />
    </svg>
  );
}
