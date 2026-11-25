"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { EventLane, EventLegend, layoutEvents } from "@/components/charts/event-lane";
import { TimeAxis, type Plot } from "@/components/charts/time-axis";
import { DAY, dayMs, niceTicks, timeScale, timeTicks, type Domain } from "@/components/charts/time-scale";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { useI18n } from "@/lib/i18n/client";
import type { Context, SignalPoint } from "@/lib/types";
import { weekOf, type Week } from "./activity-model";
import { pointsIn } from "./metric-model";

const MIN_DAY_PX = 4;
const AXIS_W = 44;

type Props = { points: SignalPoint[]; weeks: Week[]; domain: Domain; context: Context | null };

/** Daily steps as bars with the weekly average as a line on the shared time axis; scrolls inside its card when the
 *  period has more days than fit, and starts at the latest day. */
export function StepsChart({ points, weeks, domain, context }: Props) {
  const i18n = useI18n();
  const { t, formatNumber, formatDate } = i18n;
  const [measure, width] = useChartWidth();
  const scroller = useRef<HTMLDivElement | null>(null);
  const setScroller = useCallback((el: HTMLDivElement | null) => { scroller.current = el; measure(el); }, [measure]);
  const [active, setActive] = useState<number | null>(null);

  const compact = width < 520;
  const days = (domain[1] - domain[0]) / DAY;
  const innerW = Math.max(width, Math.ceil(days * MIN_DAY_PX) + 32);
  const plot: Plot = { left: 16, right: innerW - 16, top: 16, bottom: 16 + (compact ? 180 : 220) };
  const x = useMemo(() => timeScale(domain, plot.left, plot.right), [domain, plot.left, plot.right]);
  const shown = useMemo(() => pointsIn(points, domain), [points, domain]);
  const shownWeeks = weeks.filter((w) => w.mid >= domain[0] && w.mid <= domain[1]);

  const max = Math.max(1000, ...shown.map((p) => p.value), ...shownWeeks.map((w) => w.mean));
  const { domain: [, yMax], ticks: yTicks } = niceTicks(0, max, compact ? 4 : 5);
  const y = (v: number) => plot.bottom - (v / (yMax || 1)) * (plot.bottom - plot.top);
  const ticks = useMemo(() => timeTicks(domain, Math.floor((plot.right - plot.left) / (compact ? 64 : 84))), [domain, plot.left, plot.right, compact]);
  const events = useMemo(() => layoutEvents(context, domain, x, i18n), [context, domain, x, i18n]);
  const axisBottom = plot.bottom + 26;
  const totalH = axisBottom + events.height + 6;

  const dayPx = x(domain[0] + DAY) - x(domain[0]);
  const barW = Math.max(1.5, Math.min(14, dayPx * 0.7));
  const cxOf = (iso: string) => x(dayMs(iso) + DAY / 2);
  // A week with no steps at all breaks the line instead of being bridged (half a day of slack for DST).
  const line = shownWeeks.map((w, i) => `${i && w.mid - shownWeeks[i - 1].mid <= 7.5 * DAY ? "L" : "M"}${x(w.mid).toFixed(1)} ${y(w.mean).toFixed(1)}`).join(" ");
  const steps = (v: number) => formatNumber(v, { maximumFractionDigits: 0 });

  useEffect(() => { const el = scroller.current; if (el) el.scrollLeft = el.scrollWidth; }, [innerW, domain]);
  const cur = active !== null ? shown[Math.min(active, shown.length - 1)] : shown.at(-1);
  const curWeek = cur ? weekOf(weeks, cur.date) : undefined;

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    if (!shown.length) return;
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
    let best = 0;
    shown.forEach((p, i) => { if (Math.abs(cxOf(p.date) - px) < Math.abs(cxOf(shown[best].date) - px)) best = i; });
    setActive(best);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    const i = active ?? shown.length - 1;
    const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: shown.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const k = Math.min(shown.length - 1, Math.max(0, next));
    setActive(k);
    // Keep the chosen day in view inside the scrolling card.
    const el = scroller.current, px = cxOf(shown[k].date);
    if (el && (px < el.scrollLeft + 16 || px > el.scrollLeft + el.clientWidth - 16)) el.scrollLeft = px - el.clientWidth / 2;
  };

  return (
    <div className="surface min-w-0 space-y-3 p-4">
      <p className="min-h-5 text-sm tnum" aria-live="polite">
        {cur ? (
          <>
            <span className="font-medium">{formatDate(cur.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</span>
            {": "}{t("activity.stepsDay", { n: steps(cur.value) })}
            {curWeek && <span className="text-muted-foreground"> · {t("activity.weekAvg", { n: steps(curWeek.mean) })}</span>}
          </>
        ) : <span className="text-muted-foreground">{t("activity.stepsNone")}</span>}
      </p>
      <div className="flex">
        <svg width={AXIS_W} height={totalH} aria-hidden className="shrink-0 font-sans">
          {yTicks.map((v) => (
            <text key={v} x={AXIS_W - 6} y={y(v) + 4} textAnchor="end" className="fill-muted-foreground text-[11px] tnum">{formatNumber(v, { notation: "compact", maximumFractionDigits: 1 })}</text>
          ))}
        </svg>
        <div ref={setScroller} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden overscroll-x-contain">
          <svg width={innerW} height={totalH} tabIndex={0} role="group" aria-label={t("activity.stepsLabel")} onKeyDown={onKey}
            onPointerMove={onMove} onPointerLeave={() => setActive(null)} className="block rounded-lg font-sans outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <g aria-hidden>
              {yTicks.map((v) => <line key={v} x1={plot.left} x2={plot.right} y1={y(v)} y2={y(v)} className="stroke-border" strokeOpacity={0.6} strokeDasharray="2 4" />)}
            </g>
            <TimeAxis ticks={ticks} x={x} plot={plot} i18n={i18n} />
            {!shown.length && (
              <text x={(plot.left + plot.right) / 2} y={(plot.top + plot.bottom) / 2} textAnchor="middle" className="fill-muted-foreground text-[13px]">{t("activity.stepsNone")}</text>
            )}
            <g aria-hidden>
              {shown.map((p) => {
                const isCur = p === cur && active !== null;
                return <rect key={p.date} x={cxOf(p.date) - barW / 2} y={y(p.value)} width={barW} height={Math.max(0, plot.bottom - y(p.value))} rx={Math.min(2, barW / 3)}
                  style={{ fill: "var(--chart-1)" }} fillOpacity={isCur ? 1 : 0.5} />;
              })}
              {line.includes("L") && (
                <>
                  <path d={line} fill="none" stroke="var(--card)" strokeWidth={5} strokeLinejoin="round" strokeLinecap="round" />
                  <path d={line} fill="none" className="stroke-foreground" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                </>
              )}
              {cur && active !== null && <line x1={cxOf(cur.date)} x2={cxOf(cur.date)} y1={plot.top} y2={plot.bottom} className="stroke-foreground" strokeOpacity={0.3} strokeDasharray="3 3" />}
            </g>
            <EventLane layout={events} plot={plot} top={axisBottom} />
          </svg>
        </div>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden>
        <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: "color-mix(in oklab, var(--chart-1) 50%, transparent)" }} />{t("activity.legendDay")}</li>
        <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded-full bg-foreground" />{t("activity.legendWeek")}</li>
      </ul>
      <EventLegend i18n={i18n} show={{ visits: events.markers.some((m) => m.kind === "visit"), imaging: events.markers.some((m) => m.kind === "imaging"), courses: events.courses.length > 0 }} />
      <p className="text-xs text-muted-foreground">{t("activity.stepsHint")}</p>
    </div>
  );
}
