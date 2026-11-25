"use client";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n/client";
import type { MarkerHistory } from "@/lib/types";
import { TimeAxis, TodayMarker, type Plot } from "./time-axis";
import { dayMs, niceTicks, timeScale, timeTicks, type Domain } from "./time-scale";
import { TooltipBox } from "./tooltip-box";
import { useChartWidth } from "./use-chart-width";

const SERIES_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];
const SHAPES = ["circle", "square", "diamond", "triangle"] as const;

function Shape({ kind, cx, cy, r, color }: { kind: (typeof SHAPES)[number]; cx: number; cy: number; r: number; color: string }) {
  const style = { fill: color, stroke: "var(--card)" };
  if (kind === "square") return <rect x={cx - r} y={cy - r} width={2 * r} height={2 * r} rx={1.5} style={style} strokeWidth={1.5} />;
  if (kind === "diamond") return <path d={`M${cx} ${cy - r - 1}L${cx + r + 1} ${cy}L${cx} ${cy + r + 1}L${cx - r - 1} ${cy}Z`} style={style} strokeWidth={1.5} />;
  if (kind === "triangle") return <path d={`M${cx} ${cy - r - 1}L${cx + r + 1} ${cy + r}L${cx - r - 1} ${cy + r}Z`} style={style} strokeWidth={1.5} />;
  return <circle cx={cx} cy={cy} r={r} style={style} strokeWidth={1.5} />;
}

type Series = { key: string; name: string; unit: string; data: { ms: number; date: string; value: number; pct: number }[] };

/** Several markers on one time axis, each normalised so 0% is its range's lower edge and 100% the upper edge. */
export function RangeOverlay({ h, others, domain, todayMs }: { h: MarkerHistory; others: { marker_key: string; display_name: string }[]; domain: Domain; todayMs: number }) {
  const i18n = useI18n();
  const { t, formatDate, formatNumber, unit } = i18n;
  const [ref, width] = useChartWidth();
  const [picked, setPicked] = useState<string[]>([]);
  const [extra, setExtra] = useState<Record<string, MarkerHistory>>({});
  const [active, setActive] = useState<{ s: number; k: number } | null>(null);
  const compact = width < 520;

  useEffect(() => {
    picked.filter((k) => !extra[k]).forEach(async (k) => {
      const r = await fetch(`/api/biomarkers/${encodeURIComponent(k)}/history`);
      if (r.ok) {
        const json: MarkerHistory = await r.json();
        setExtra((e) => ({ ...e, [k]: json }));
      }
    });
  }, [picked, extra]);

  const series: Series[] = useMemo(() => [h, ...picked.map((k) => extra[k]).filter(Boolean)].map((m) => ({
    key: m.marker_key, name: m.display_name, unit: m.unit,
    data: m.points.filter((p) => p.ref_min !== null && p.ref_max !== null && p.ref_max > p.ref_min)
      .map((p) => ({ ms: dayMs(p.date), date: p.date, value: p.value, pct: ((p.value - p.ref_min!) / (p.ref_max! - p.ref_min!)) * 100 }))
      .filter((d) => d.ms >= domain[0] && d.ms <= domain[1]),
  })), [h, picked, extra, domain]);

  const plot: Plot = { left: compact ? 44 : 54, right: width - (compact ? 14 : 20), top: 22, bottom: 22 + (compact ? 200 : 250) };
  const x = timeScale(domain, plot.left, plot.right);
  const ticks = timeTicks(domain, Math.floor((plot.right - plot.left) / (compact ? 64 : 84)));
  const pcts = series.flatMap((s) => s.data.map((d) => d.pct));
  const nice = niceTicks(Math.min(-20, ...pcts) - 5, Math.max(120, ...pcts) + 5, 5);
  const y = (v: number) => plot.bottom - ((v - nice.domain[0]) / (nice.domain[1] - nice.domain[0])) * (plot.bottom - plot.top);
  const hasRange = h.points.some((p) => p.ref_min !== null && p.ref_max !== null);
  if (!hasRange && !picked.length) return <p className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{t("charts.overlayNoRange")}</p>;

  const pct = (v: number) => `${formatNumber(v, { maximumFractionDigits: 0 })}%`;
  const nameOf = (k: string) => others.find((o) => o.marker_key === k)?.display_name ?? k;
  const a = active ? series[active.s]?.data[active.k] : null;
  const todayVisible = todayMs >= domain[0] && todayMs <= domain[1];

  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm text-muted-foreground">{t("charts.overlayHelp")}</p>
      <div className="flex flex-wrap items-center gap-2">
        {picked.map((k, i) => (
          <Badge key={k} variant="outline" className="gap-1.5">
            <span className="size-2 rounded-full" style={{ background: SERIES_COLORS[i + 1] }} />{nameOf(k)}
            <button type="button" aria-label={t("charts.removeMarker", { name: nameOf(k) })} onClick={() => setPicked(picked.filter((x) => x !== k))}>×</button>
          </Badge>
        ))}
        {picked.length < 3 && (
          <select aria-label={t("charts.addMarkerLabel")} className="h-8 rounded-xl border bg-card px-2 text-sm" value="" onChange={(e) => e.target.value && setPicked([...picked, e.target.value])}>
            <option value="">{t("charts.addMarkerPlaceholder")}</option>
            {others.filter((o) => o.marker_key !== h.marker_key && !picked.includes(o.marker_key)).map((o) => <option key={o.marker_key} value={o.marker_key}>{o.display_name}</option>)}
          </select>
        )}
      </div>
      <div ref={ref} className="relative w-full max-w-full overflow-hidden">
        <svg width={width} height={plot.bottom + 28} viewBox={`0 0 ${width} ${plot.bottom + 28}`} role="group" aria-label={t("charts.overlayLabel")} className="block overflow-visible font-sans">
          <rect x={plot.left} y={y(100)} width={plot.right - plot.left} height={y(0) - y(100)} style={{ fill: "var(--inrange)" }} fillOpacity={0.85} aria-hidden="true" />
          <text x={plot.left + 6} y={y(100) + 12} className="fill-muted-foreground text-[10px]" aria-hidden="true">{t("charts.insideRange")}</text>
          <g aria-hidden="true">
            {nice.ticks.map((v) => <g key={v}><line x1={plot.left} x2={plot.right} y1={y(v)} y2={y(v)} className="stroke-border" strokeOpacity={0.6} strokeDasharray="2 4" /><text x={plot.left - 8} y={y(v) + 4} textAnchor="end" className="fill-muted-foreground text-[11px]">{pct(v)}</text></g>)}
          </g>
          <TimeAxis ticks={ticks} x={x} plot={plot} i18n={i18n} />
          {todayVisible && <TodayMarker px={x(todayMs)} plot={plot} label={t("charts.today")} />}
          {series.map((s, si) => {
            const color = SERIES_COLORS[si];
            const end = s.data.at(-1);
            return (
              <g key={s.key}>
                {s.data.length >= 2 && <path d={s.data.map((d, k) => `${k ? "L" : "M"}${x(d.ms).toFixed(1)} ${y(d.pct).toFixed(1)}`).join(" ")} fill="none" strokeWidth={2} strokeLinejoin="round" style={{ stroke: color }} strokeDasharray={s.data.length < 3 ? "4 4" : undefined} />}
                {s.data.map((d, k) => (
                  <g key={d.date} tabIndex={0} role="img" aria-label={`${s.name}, ${formatDate(d.date)}: ${formatNumber(d.value, { maximumFractionDigits: 4 })} ${unit(s.unit)}, ${pct(d.pct)}`} className="cursor-pointer outline-none"
                    onMouseEnter={() => setActive({ s: si, k })} onMouseLeave={() => setActive(null)} onFocus={() => setActive({ s: si, k })} onBlur={() => setActive(null)}>
                    <circle cx={x(d.ms)} cy={y(d.pct)} r={16} fill="transparent" />
                    <Shape kind={SHAPES[si]} cx={x(d.ms)} cy={y(d.pct)} r={active?.s === si && active.k === k ? 6.5 : 4.5} color={color} />
                  </g>
                ))}
                {end && !compact && <text x={Math.min(x(end.ms) + 8, plot.right - 4)} y={y(end.pct) - 10} textAnchor={x(end.ms) > plot.right - 90 ? "end" : "start"} className="text-[11px] font-medium" style={{ fill: color, paintOrder: "stroke", stroke: "var(--card)", strokeWidth: 3 }}>{s.name}</text>}
              </g>
            );
          })}
        </svg>
        {a && active && (
          <TooltipBox x={x(a.ms)} y={y(a.pct)} width={width}>
            <div className="font-medium">{series[active.s].name}</div>
            <div className="tnum">{formatDate(a.date)}</div>
            <div className="tnum"><span className="font-semibold">{formatNumber(a.value, { maximumFractionDigits: 4 })}</span> <span className="text-muted-foreground">{unit(series[active.s].unit)}</span></div>
            <div className="text-xs text-muted-foreground tnum">{t("charts.positionInRange", { pct: pct(a.pct) })}</div>
          </TooltipBox>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label={t("charts.legendSeries")}>
        {series.map((s, si) => <li key={s.key} className="flex items-center gap-1.5"><svg width="12" height="12" aria-hidden="true"><Shape kind={SHAPES[si]} cx={6} cy={6} r={4} color={SERIES_COLORS[si]} /></svg>{s.name}</li>)}
      </ul>
    </div>
  );
}
