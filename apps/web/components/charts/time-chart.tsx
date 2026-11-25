"use client";
import { useMemo, useState, type FocusEvent, type KeyboardEvent } from "react";
import { DemoBadge } from "@/components/demo-badge";
import { useI18n } from "@/lib/i18n/client";
import type { Context, HistoryPoint, MarkerTier } from "@/lib/types";
import { Bands, tierRangeText } from "./bands";
import { arrowOf, classifyChange, rangeSide, signOf, type Change } from "./change";
import { durationLabel } from "./duration";
import { EventLane, EventLegend, layoutEvents } from "./event-lane";
import { TimeAxis, TodayMarker, type Plot } from "./time-axis";
import { DAY, dayMs, niceTicks, timeScale, timeTicks, type Domain } from "./time-scale";
import { tierOf, tiersUnit } from "./tiers";
import { unitsCompatible } from "./units";
import { TooltipBox } from "./tooltip-box";
import { useChartWidth } from "./use-chart-width";

/** `note`: one extra line for the tooltip (e.g. a night's lowest value next to its average). */
export type ChartPoint = HistoryPoint & { lab_name?: string | null; note?: string | null };

const GAP_DAYS = 90;
const MOTION_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .tc-line { stroke-dasharray: 1; stroke-dashoffset: 1; animation: tc-draw 900ms ease-out forwards; }
  .tc-fade { opacity: 0; animation: tc-fade 500ms ease-out 500ms forwards; }
  .tc-dot { transition: r 120ms ease-out, opacity 120ms ease-out; }
}
@keyframes tc-draw { to { stroke-dashoffset: 0; } }
@keyframes tc-fade { to { opacity: 1; } }
`;

type Props = {
  name: string;
  unit: string;
  points: ChartPoint[]; // all results, oldest first
  tiers: MarkerTier[];
  context: Context | null;
  domain: Domain;
  todayMs: number;
  /** Doctor/print mode: drawn at once (no draw-in animation) and no hover/focus highlight. */
  staticMode?: boolean;
  /** "usual": the ref band is the owner's own usual range, not a lab norm: worded as such and never coloured as good or bad. */
  band?: "reference" | "usual";
};

/** Label slots: highest priority first (latest, out of range, first, rest); skip any that would touch an accepted one. */
function pickLabels(xs: number[], priority: number[], gap: number): Set<number> {
  const taken: number[] = [];
  const out = new Set<number>();
  for (const i of priority) {
    if (taken.every((x) => Math.abs(x - xs[i]) >= gap)) { taken.push(xs[i]); out.add(i); }
  }
  return out;
}

export function TimeChart({ name, unit: unitCode, points, tiers, context, domain, todayMs, staticMode = false, band = "reference" }: Props) {
  const i18n = useI18n();
  const { t, tp, formatNumber, formatDate, unit } = i18n;
  const [ref, width] = useChartWidth();
  const [active, setActive] = useState<number | null>(null);
  const compact = width < 520;
  // Tiers are valid only in the unit they were printed in; points in another unit are not judged by them.
  const tierUnit = tiersUnit(tiers);
  const otherUnitCount = tiers.length ? points.filter((p) => !unitsCompatible(p.unit, tierUnit)).length : 0;
  const num = (v: number, digits = 2) => formatNumber(v, { maximumFractionDigits: digits });

  const plot: Plot = { left: compact ? 40 : 52, right: width - (compact ? 14 : 20), top: 22, bottom: 22 + (compact ? 210 : 270) };
  const x = useMemo(() => timeScale(domain, plot.left, plot.right), [domain, plot.left, plot.right]);

  const visible = useMemo(() => points.map((p, i) => ({ p, i, ms: dayMs(p.date) })).filter((v) => v.ms >= domain[0] && v.ms <= domain[1]), [points, domain]);
  const latest = visible.at(-1)?.p ?? points.at(-1);
  const refRange = latest ? { min: latest.ref_min, max: latest.ref_max } : null;

  const vals = visible.map((v) => v.p.value);
  if (refRange?.min != null) vals.push(refRange.min);
  if (refRange?.max != null) vals.push(refRange.max);
  if (!vals.length) vals.push(0, 1);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const yPad = (hi - lo || Math.abs(hi) * 0.2 || 1) * 0.15;
  let nice = niceTicks(lo - yPad, hi + yPad, compact ? 4 : 5);
  if (lo >= 0 && nice.domain[0] < 0) nice = niceTicks(0, hi + yPad, compact ? 4 : 5);
  const [d0, d1] = nice.domain;
  const yTicks = nice.ticks;
  const yScale = (v: number) => plot.bottom - ((v - d0) / (d1 - d0 || 1)) * (plot.bottom - plot.top);

  const ticks = useMemo(() => timeTicks(domain, Math.floor((plot.right - plot.left) / (compact ? 64 : 84))), [domain, plot.left, plot.right, compact]);
  const events = useMemo(() => layoutEvents(context, domain, x, i18n), [context, domain, x, i18n]);
  const axisBottom = plot.bottom + 26;
  const totalH = axisBottom + events.height + 6;

  const xs = visible.map((v) => x(v.ms));
  const rank = (k: number) => (k === visible.length - 1 ? 0 : visible[k].p.out_of_range ? 1 : k === 0 ? 2 : 3);
  const usual = band === "usual";
  // Usual-band (daily) charts only: a dense series (more than one point per 6 px) reads as a line, with no dots or
  // value labels except the latest and the one in focus. Reference charts keep every dot and label.
  const dense = usual && visible.length > 1 && (plot.right - plot.left) / visible.length < 6;
  const labelled = dense ? new Set([visible.length - 1]) : pickLabels(xs, visible.map((_, k) => k).sort((a, b) => rank(a) - rank(b)), compact ? 40 : 50);

  const lineD = visible.map((v, k) => `${k ? "L" : "M"}${xs[k].toFixed(1)} ${yScale(v.p.value).toFixed(1)}`).join(" ");
  const areaD = visible.length >= 3 ? `${lineD} L${xs.at(-1)!.toFixed(1)} ${plot.bottom} L${xs[0].toFixed(1)} ${plot.bottom} Z` : "";
  const enough = visible.length >= 3;
  const todayVisible = todayMs >= domain[0] && todayMs <= domain[1];
  const u = unit(unitCode);
  // Usual-band charts get smaller dots and hit areas as days crowd together; reference charts keep r=5 and an 18 px hit area.
  const spacing = visible.length > 1 ? (plot.right - plot.left) / visible.length : 99;
  const dotR = usual ? Math.min(5, Math.max(2.5, spacing / 2.2)) : 5;
  const hitR = usual ? Math.min(18, Math.max(8, spacing)) : 18;
  const ringR = usual ? Math.max(dotR, 4) + 6 : 11;
  const activeR = usual ? Math.max(dotR, 4) + 1.5 : 6.5;
  // Usual-band charts are one tab stop: arrow keys move through the days and a live region reads the day out.
  const roving = usual && !staticMode;
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const i = active ?? visible.length - 1;
    const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: visible.length - 1 }[e.key];
    if (next === undefined || !visible.length) return;
    e.preventDefault();
    setActive(Math.min(visible.length - 1, Math.max(0, next)));
  };

  const sideWord = (p: ChartPoint) => (usual
    ? { below: t("charts.usualBelow"), above: t("charts.usualAbove"), within: t("charts.usualWithin"), none: "" }
    : { below: t("charts.sideBelow"), above: t("charts.sideAbove"), within: t("charts.sideWithin"), none: t("charts.sideNone") })[rangeSide(p)];
  const changeText = (c: Change, long: boolean) => {
    const abs = `${signOf(c.abs)}${num(Math.abs(c.abs))}`;
    const pct = c.pct === null ? "" : ` · ${signOf(c.pct)}${num(Math.abs(c.pct), 1)}%`;
    const verdict = long && !usual ? ({ toward: ` · ${t("charts.toward")}`, away: ` · ${t("charts.away")}`, stayed: ` · ${t("charts.stayed")}`, unknown: "" })[c.judgement] : "";
    return `${arrowOf(c.direction)} ${abs}${pct}${verdict}`;
  };
  const judgementColor = (c: Change) => (usual ? "var(--muted-foreground)" : c.judgement === "toward" ? "var(--ok)" : c.judgement === "away" ? "var(--outrange)" : "var(--muted-foreground)");
  const pointLabel = (p: ChartPoint) => {
    const tier = tierOf(tiers, p.value, p.unit);
    return `${formatDate(p.date)}: ${num(p.value, 4)} ${u}. ${tier ? `${tier.label}. ` : ""}${sideWord(p)}${p.note ? `. ${p.note}` : ""}${p.date_suspect ? `. ${t("common.dateUnverified")}` : ""}`;
  };

  const activeV = active !== null ? visible[active] : null;
  const activePrev = activeV && activeV.i > 0 ? points[activeV.i - 1] : null;
  const activeTier = activeV ? tierOf(tiers, activeV.p.value, activeV.p.unit) : undefined;
  const activeChange = activeV && activePrev ? classifyChange(activePrev, activeV.p) : null;
  const lastVisible = visible.at(-1);
  const trailGap = lastVisible && todayVisible ? Math.round((todayMs - lastVisible.ms) / DAY) : 0;

  return (
    <div>
      <div ref={ref} className="relative w-full max-w-full overflow-hidden">
        {!staticMode && <style>{MOTION_CSS}</style>}
        <svg width={width} height={totalH} viewBox={`0 0 ${width} ${totalH}`} role="group" aria-label={roving ? t("charts.chartKeysLabel", { name }) : t("charts.chartLabel", { name })}
          className={roving ? "block overflow-visible rounded-lg font-sans outline-none focus-visible:ring-2 focus-visible:ring-ring" : "block overflow-visible font-sans"}
          {...(roving ? { tabIndex: 0, onKeyDown: onKey, onFocus: (e: FocusEvent<SVGSVGElement>) => { if (e.target === e.currentTarget) setActive((a) => a ?? visible.length - 1); },
            onBlur: (e: FocusEvent<SVGSVGElement>) => { if (e.target === e.currentTarget) setActive(null); } } : {})}>
          <defs>
            <linearGradient id="tc-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" style={{ stopColor: "var(--chart-1)", stopOpacity: 0.28 }} />
              <stop offset="100%" style={{ stopColor: "var(--chart-1)", stopOpacity: 0 }} />
            </linearGradient>
          </defs>
          <Bands y={yScale} plot={plot} tiers={tiers} refRange={refRange} i18n={i18n} usual={usual} />
          <g aria-hidden="true">
            {yTicks.map((v) => {
              const py = yScale(v);
              if (py < plot.top - 1 || py > plot.bottom + 1) return null;
              return (
                <g key={v}>
                  <line x1={plot.left} x2={plot.right} y1={py} y2={py} className="stroke-border" strokeOpacity={0.6} strokeDasharray="2 4" />
                  <text x={plot.left - 8} y={py + 4} textAnchor="end" className="fill-muted-foreground text-[11px]">{num(v)}</text>
                </g>
              );
            })}
            {u && <text x={plot.left - 8} y={plot.top - 8} textAnchor="end" className="fill-muted-foreground text-[10px]">{u}</text>}
          </g>
          <TimeAxis ticks={ticks} x={x} plot={plot} i18n={i18n} />
          {todayVisible && <TodayMarker px={x(todayMs)} plot={plot} label={t("charts.today")} />}

          {!visible.length && (
            <text x={(plot.left + plot.right) / 2} y={(plot.top + plot.bottom) / 2} textAnchor="middle" className="fill-muted-foreground text-[13px]">{t("charts.noneInPeriod")}</text>
          )}

          {areaD && <path d={areaD} fill="url(#tc-area)" className="tc-fade" />}
          {visible.length >= 2 && (
            <path d={lineD} pathLength={enough ? 1 : undefined} fill="none" strokeLinejoin="round" strokeLinecap="round" strokeWidth={enough ? 2 : 1.5} strokeDasharray={enough ? undefined : "4 4"}
              style={{ stroke: "var(--chart-1)" }} className={enough ? "tc-line" : "tc-fade"} />
          )}

          {/* gaps between results that are long enough to matter */}
          <g aria-hidden="true">
            {visible.slice(1).map((v, k) => {
              const prev = visible[k];
              const days = Math.round((v.ms - prev.ms) / DAY);
              const w = xs[k + 1] - xs[k];
              if (days < GAP_DAYS || w < 120) return null;
              const gy = plot.bottom - 8;
              return (
                <g key={`gap${v.i}`}>
                  <path d={`M${xs[k] + 6} ${gy - 4}V${gy + 2}M${xs[k] + 6} ${gy}H${xs[k + 1] - 6}M${xs[k + 1] - 6} ${gy - 4}V${gy + 2}`} fill="none" className="stroke-muted-foreground" strokeOpacity={0.7} />
                  <text x={(xs[k] + xs[k + 1]) / 2} y={gy - 6} textAnchor="middle" className="fill-muted-foreground text-[10.5px]">{t("charts.gapNone", { duration: durationLabel(i18n, days) })}</text>
                </g>
              );
            })}
            {lastVisible && trailGap >= GAP_DAYS && x(todayMs) - xs.at(-1)! >= 120 && (
              <g>
                <path d={`M${xs.at(-1)! + 6} ${plot.bottom - 12}V${plot.bottom - 6}M${xs.at(-1)! + 6} ${plot.bottom - 8}H${x(todayMs) - 6}M${x(todayMs) - 6} ${plot.bottom - 12}V${plot.bottom - 6}`} fill="none" className="stroke-muted-foreground" strokeOpacity={0.7} />
                <text x={(xs.at(-1)! + x(todayMs)) / 2} y={plot.bottom - 14} textAnchor="middle" className="fill-muted-foreground text-[10.5px]">{t("charts.gapSince", { duration: durationLabel(i18n, trailGap) })}</text>
              </g>
            )}
          </g>

          {/* change between consecutive points, on the line */}
          <g aria-hidden="true">
            {visible.slice(1).map((v, k) => {
              const prev = visible[k];
              const w = xs[k + 1] - xs[k];
              if (w < (compact ? 84 : 92)) return null;
              const c = classifyChange(prev.p, v.p);
              const long = w >= 190;
              const text = changeText(c, long);
              const pw = text.length * 6.1 + 12;
              const mx = (xs[k] + xs[k + 1]) / 2, my = (yScale(prev.p.value) + yScale(v.p.value)) / 2;
              const py = my + 24 < plot.bottom - 22 ? my + 14 : my - 30;
              return (
                <g key={`chg${v.i}`}>
                  <rect x={mx - pw / 2} y={py} width={pw} height={18} rx={9} style={{ fill: "var(--card)", stroke: judgementColor(c) }} strokeOpacity={0.8} />
                  <text x={mx} y={py + 12.5} textAnchor="middle" className="text-[10.5px] font-medium" style={{ fill: judgementColor(c) }}>{text}</text>
                </g>
              );
            })}
          </g>

          {activeV && <line x1={xs[active!]} x2={xs[active!]} y1={plot.top} y2={plot.bottom} className="stroke-foreground" strokeOpacity={0.35} strokeDasharray="3 3" aria-hidden="true" />}

          {visible.map((v, k) => {
            const cx = xs[k], cy = yScale(v.p.value);
            const out = v.p.out_of_range;
            const color = out ? "var(--outrange)" : "var(--chart-1)";
            const isActive = active === k;
            const below = cy < plot.top + 16;
            const side = rangeSide(v.p);
            return (
              <g key={v.i} {...(roving ? {
                "aria-hidden": true, className: "cursor-pointer",
                onMouseEnter: () => setActive(k), onMouseLeave: () => setActive((a) => (a === k ? null : a)),
              } : { role: "img", "aria-label": pointLabel(v.p) })} {...(staticMode || roving ? {} : {
                tabIndex: 0, className: "cursor-pointer outline-none",
                onMouseEnter: () => setActive(k), onMouseLeave: () => setActive((a) => (a === k ? null : a)), onFocus: () => setActive(k), onBlur: () => setActive((a) => (a === k ? null : a)),
              })}>
                <circle cx={cx} cy={cy} r={hitR} fill="transparent" />
                {isActive && <circle cx={cx} cy={cy} r={ringR} fill="none" strokeWidth={2} style={{ stroke: color }} strokeOpacity={0.5} />}
                {out && !isActive && <circle cx={cx} cy={cy} r={9} fill="none" strokeWidth={1.5} style={{ stroke: color }} strokeOpacity={0.45} />}
                <circle className="tc-dot" cx={cx} cy={cy} r={isActive ? activeR : dense && !labelled.has(k) ? 0 : dotR} strokeWidth={2} strokeDasharray={v.p.date_suspect ? "2 2" : undefined}
                  style={{ fill: v.p.date_suspect ? "var(--card)" : color, stroke: color }} />
                {(labelled.has(k) || isActive) && (
                  <text x={cx} y={below ? cy + 22 : cy - 12} textAnchor="middle" className="tnum text-[11.5px]" style={{ fill: out ? "var(--outrange)" : "var(--foreground)", fontWeight: out || isActive ? 700 : 500, paintOrder: "stroke", stroke: "var(--card)", strokeWidth: 3 }}>
                    {out && side !== "within" && side !== "none" ? `${side === "above" ? "▲" : "▼"} ` : ""}{num(v.p.value)}
                  </text>
                )}
              </g>
            );
          })}

          <EventLane layout={events} plot={plot} top={axisBottom} />
        </svg>
        {roving && <p className="sr-only" aria-live="polite">{activeV ? pointLabel(activeV.p) : ""}</p>}

        {activeV && (
          <TooltipBox x={xs[active!]} y={yScale(activeV.p.value)} width={width}>
            <div className="font-medium tnum">{formatDate(activeV.p.date)}</div>
            <div className="tnum text-base">
              <span className={activeV.p.out_of_range ? "font-semibold text-outrange" : "font-semibold"}>{num(activeV.p.value, 4)}</span> <span className="text-muted-foreground">{u}</span>
            </div>
            <div className="text-xs">
              {activeTier ? <span className="font-medium">{activeTier.label}{tierRangeText(i18n, activeTier) ? `: ${tierRangeText(i18n, activeTier)}` : ""}</span> : <span className={activeV.p.out_of_range ? "font-medium text-outrange" : ""}>{sideWord(activeV.p)}</span>}
            </div>
            {activeV.p.note && <div className="text-xs tnum">{activeV.p.note}</div>}
            {activeV.p.ref_min !== null && activeV.p.ref_max !== null && (
              <div className="text-xs text-muted-foreground tnum">{t(usual ? "charts.usualBand" : "charts.refBand", { range: `${num(activeV.p.ref_min)}–${num(activeV.p.ref_max)}` })}</div>
            )}
            {activeChange && activePrev && (
              <div className="mt-1 text-xs tnum" style={{ color: judgementColor(activeChange) }}>
                {t("charts.sincePrevious", { date: formatDate(activePrev.date, { day: "numeric", month: "short", year: "numeric" }) })}: {changeText(activeChange, true)}
              </div>
            )}
            {activeV.p.lab_name && <div className="text-xs text-muted-foreground">{t("charts.lab", { name: activeV.p.lab_name })}</div>}
            {activeV.p.date_suspect && <div className="text-xs" style={{ color: "var(--warn)" }}>{t("common.dateUnverified")}</div>}
            {activeV.p.is_demo && <div className="mt-1"><DemoBadge /></div>}
          </TooltipBox>
        )}
      </div>
      {otherUnitCount > 0 && <p className="mt-2 text-xs text-muted-foreground">{tp("charts.tierUnitNote", otherUnitCount, { unit: unit(tierUnit ?? "") })}</p>}
      <EventLegend i18n={i18n} show={{ visits: events.markers.some((m) => m.kind === "visit"), imaging: events.markers.some((m) => m.kind === "imaging"), courses: events.courses.length > 0 }} />
    </div>
  );
}
