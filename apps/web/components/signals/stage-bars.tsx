"use client";
import { useCallback, useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import { EventLane, EventLegend, layoutEvents } from "@/components/charts/event-lane";
import { TimeAxis, type Plot } from "@/components/charts/time-axis";
import { DAY, dayMs, niceTicks, timeScale, timeTicks, type Domain } from "@/components/charts/time-scale";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { useI18n } from "@/lib/i18n/client";
import type { ClientI18n } from "@/lib/i18n/client-core";
import type { Context } from "@/lib/types";
import { duration } from "./format";
import { STAGE, STAGES, type Grouping, type Slot } from "./sleep-model";

const STACK = ["deep", "light", "rem", "awake"] as const; // bottom to top
const MIN_SLOT_PX: Record<Grouping, number> = { night: 6, week: 10, month: 18 };
const SLOT_DAYS: Record<Grouping, number> = { night: 1, week: 7, month: 30.4 };
const AXIS_W = 36;

type Props = {
  slots: Slot[]; grouping: Grouping; domain: Domain; context: Context | null;
  selectedId: number | null; onSelect: (sessionId: number, reveal: boolean) => void;
};

function slotLabel(i18n: ClientI18n, s: Slot, g: Grouping): string {
  const { t, tp, formatDate } = i18n;
  const stages = !s.staged ? t("signals.noStages")
    : STAGES.map((st) => t("signals.stageTime", { name: t(st.label), time: duration(i18n, s.avg[st.key]).long })).join(", ")
      + (s.staged < s.nights.length ? `. ${t("signals.stagesFrom", { k: s.staged, n: s.nights.length })}` : "");
  const total = duration(i18n, s.avg.duration_min).long;
  if (g === "night") return t("signals.barNight", { date: formatDate(s.from, { weekday: "short", day: "numeric", month: "long", year: "numeric" }), total, stages });
  const range = g === "month" ? formatDate(s.from, { month: "long", year: "numeric" })
    : t("signals.range", { from: formatDate(s.from, { day: "numeric", month: "short" }), to: formatDate(s.to, { day: "numeric", month: "short", year: "numeric" }) });
  return tp("signals.barGroup", s.nights.length, { range, total, stages });
}

export function StageBars({ slots, grouping, domain, context, selectedId, onSelect }: Props) {
  const i18n = useI18n();
  const { t } = i18n;
  const [measure, width] = useChartWidth();
  const scroller = useRef<HTMLDivElement | null>(null);
  const setScroller = useCallback((el: HTMLDivElement | null) => { scroller.current = el; measure(el); }, [measure]);

  const compact = width < 520;
  const spanSlots = (domain[1] - domain[0]) / DAY / SLOT_DAYS[grouping];
  const innerW = Math.max(width, Math.ceil(spanSlots * MIN_SLOT_PX[grouping]) + 24);
  const plot: Plot = { left: 24, right: innerW - 24, top: 26, bottom: 26 + (compact ? 180 : 230) };
  const x = useMemo(() => timeScale(domain, plot.left, plot.right), [domain, plot.left, plot.right]);

  const maxMin = Math.max(60, ...slots.map((s) => Math.max(s.avg.duration_min, STACK.reduce((a, k) => a + Math.max(0, s.avg[k]), 0))));
  const { domain: [, yMax], ticks: yTicks } = niceTicks(0, maxMin / 60, 5);
  const y = (minutes: number) => plot.bottom - (minutes / 60 / (yMax || 1)) * (plot.bottom - plot.top);

  const ticks = useMemo(() => timeTicks(domain, Math.floor((plot.right - plot.left) / (compact ? 64 : 84))), [domain, plot.left, plot.right, compact]);
  const events = useMemo(() => layoutEvents(context, domain, x, i18n), [context, domain, x, i18n]);
  const axisBottom = plot.bottom + 26;
  const totalH = axisBottom + events.height + 6;

  const geo = slots.map((s) => {
    const x0 = x(dayMs(s.from)), x1 = x(dayMs(s.to) + DAY);
    const w = Math.min(36, Math.max(2, (x1 - x0) * 0.72));
    return { cx: (x0 + x1) / 2, w, hit: Math.max(w, Math.min(Math.max(w, 10) + 4, x1 - x0)) }; // hit area never wider than the slot
  });
  const selectedIdx = slots.findIndex((s) => s.nights.some((n) => n.session_id === selectedId));
  const active = selectedIdx >= 0 ? selectedIdx : slots.length - 1;
  const latestOf = (s: Slot) => s.nights.at(-1)!.session_id;

  // Keep the active bar in view (the latest one on first paint).
  const activeX = geo[active]?.cx;
  useEffect(() => {
    const el = scroller.current;
    if (!el || activeX === undefined) return;
    if (activeX < el.scrollLeft + 16 || activeX > el.scrollLeft + el.clientWidth - 16) el.scrollLeft = activeX - el.clientWidth / 2;
  }, [activeX, innerW]);

  const onKey = (e: KeyboardEvent<SVGGElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: 1, ArrowDown: -1 }[e.key];
    const next = e.key === "Home" ? 0 : e.key === "End" ? slots.length - 1 : step !== undefined ? Math.min(slots.length - 1, Math.max(0, active + step)) : null;
    if (next === null) return;
    e.preventDefault();
    onSelect(latestOf(slots[next]), false);
    requestAnimationFrame(() => scroller.current?.querySelector<SVGGElement>(`[data-bar="${next}"]`)?.focus());
  };

  return (
    <div className="surface min-w-0 space-y-3 p-4">
      <div className="flex">
        <svg width={AXIS_W} height={totalH} aria-hidden className="shrink-0 font-sans">
          {yTicks.map((v) => (
            <text key={v} x={AXIS_W - 6} y={y(v * 60) + 4} textAnchor="end" className="fill-muted-foreground text-[11px] tnum">{i18n.formatNumber(v)}</text>
          ))}
          <text x={AXIS_W - 6} y={10} textAnchor="end" className="fill-muted-foreground text-[10px]">{t("signals.hoursUnit")}</text>
        </svg>
        <div ref={setScroller} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden overscroll-x-contain">
          <svg width={innerW} height={totalH} className="block font-sans">
            <defs>
              <pattern id="unstaged" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="5" className="stroke-muted-foreground" strokeWidth={1.5} strokeOpacity={0.6} />
              </pattern>
            </defs>
            <g aria-hidden>
              {yTicks.map((v) => <line key={v} x1={plot.left} x2={plot.right} y1={y(v * 60)} y2={y(v * 60)} className="stroke-border" strokeOpacity={0.6} strokeDasharray="2 4" />)}
            </g>
            <TimeAxis ticks={ticks} x={x} plot={plot} i18n={i18n} />
            {!slots.length && (
              <text x={(plot.left + plot.right) / 2} y={(plot.top + plot.bottom) / 2} textAnchor="middle" className="fill-muted-foreground text-[13px]">{t("signals.barsNone")}</text>
            )}
            <g role="radiogroup" aria-label={t("signals.barsLabel")} onKeyDown={onKey}>
              {slots.map((s, i) => {
                const { cx, w, hit } = geo[i];
                const isSel = i === selectedIdx;
                let base = 0;
                return (
                  <g key={s.key} data-bar={i} role="radio" aria-checked={isSel} aria-label={slotLabel(i18n, s, grouping)} tabIndex={i === active ? 0 : -1}
                    onClick={() => onSelect(latestOf(s), true)} className="group cursor-pointer outline-none">
                    <rect x={cx - hit / 2} y={plot.top - 6} width={hit} height={plot.bottom - plot.top + 6} rx={4}
                      className={isSel ? "fill-muted stroke-foreground/30" : "fill-transparent group-hover:fill-muted/60 group-focus-visible:stroke-ring"} strokeWidth={1.5} />
                    {!s.staged && s.avg.duration_min > 0 && (
                      <rect x={cx - w / 2 + 0.5} y={y(s.avg.duration_min)} width={Math.max(1, w - 1)} height={Math.max(0, plot.bottom - y(s.avg.duration_min))}
                        fill="url(#unstaged)" className="stroke-muted-foreground" strokeWidth={1} />
                    )}
                    {STACK.map((k) => {
                      const m = s.staged ? Math.max(0, s.avg[k]) : 0;
                      if (!m) return null;
                      const top = y(base + m), bottom = y(base);
                      const seam = base > 0;
                      base += m;
                      return (
                        <g key={k}>
                          <rect x={cx - w / 2} y={top} width={w} height={Math.max(0, bottom - top)} style={{ fill: STAGE[k].color }} />
                          {seam && <line x1={cx - w / 2} x2={cx + w / 2} y1={bottom} y2={bottom} stroke="var(--card)" strokeWidth={1} />}
                        </g>
                      );
                    })}
                    {s.avg.duration_min > 0 && <line x1={cx - w / 2 - 2} x2={cx + w / 2 + 2} y1={y(s.avg.duration_min)} y2={y(s.avg.duration_min)} className="stroke-foreground" strokeWidth={2} strokeLinecap="round" />}
                  </g>
                );
              })}
            </g>
            <EventLane layout={events} plot={plot} top={axisBottom} />
          </svg>
        </div>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden>
        {[...STACK].reverse().map((k) => (
          <li key={k} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: STAGE[k].color }} />{t(STAGE[k].label)}</li>
        ))}
        <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded-full bg-foreground" />{t("signals.barsTotal")}</li>
        {slots.some((s) => !s.staged) && (
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm border border-muted-foreground" style={{ background: "repeating-linear-gradient(45deg, var(--muted-foreground) 0 1px, transparent 1px 4px)" }} />{t("signals.noStages")}
          </li>
        )}
      </ul>
      <EventLegend i18n={i18n} show={{ visits: events.markers.some((m) => m.kind === "visit"), imaging: events.markers.some((m) => m.kind === "imaging"), courses: events.courses.length > 0 }} />
      <p className="text-xs text-muted-foreground">{t("signals.barsNote")} {slots.some((s) => s.staged < s.nights.length) && `${t("signals.unstagedNote")} `}{t(grouping === "night" ? "signals.barsHintNight" : "signals.barsHintGroup")}</p>
    </div>
  );
}
