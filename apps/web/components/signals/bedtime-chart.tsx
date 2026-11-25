"use client";
import { useMemo } from "react";
import { TimeAxis, TodayMarker, type Plot } from "@/components/charts/time-axis";
import { DAY, dayMs, timeScale, timeTicks, type Domain } from "@/components/charts/time-scale";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { useI18n } from "@/lib/i18n/client";
import type { SleepNight } from "@/lib/types";
import { clockCut, clockIso, clockOf, clockSpread } from "./sleep-model";

const BED = "var(--chart-4)";
const WAKE = "var(--chart-1)";
const HOUR_STEPS = [1, 2, 3, 4, 6];

type Props = { nights: SleepNight[]; domain: Domain; todayMs: number; selectedId: number | null };

/** Falling-asleep and wake-up clock times per night on one clock axis that runs through midnight (evening at the top). */
export function BedtimeChart({ nights, domain, todayMs, selectedId }: Props) {
  const i18n = useI18n();
  const { t, formatTime } = i18n;
  const [ref, width] = useChartWidth();
  const compact = width < 520;
  const plot: Plot = { left: compact ? 46 : 54, right: width - (compact ? 14 : 96), top: 22, bottom: 22 + (compact ? 200 : 240) };
  const x = useMemo(() => timeScale(domain, plot.left, plot.right), [domain, plot.left, plot.right]);

  const rows = nights.map((n) => ({ n, bed: clockOf(n.start_local), wake: clockOf(n.end_local) }));
  const shift = clockCut(rows.flatMap((r) => [r.bed, r.wake]));
  const all = rows.flatMap((r) => [shift(r.bed), shift(r.wake)]);
  const lo = all.length ? Math.floor((Math.min(...all) - 20) / 60) * 60 : 22 * 60;
  const hi = all.length ? Math.ceil((Math.max(...all) + 20) / 60) * 60 : 32 * 60;
  const y = (m: number) => plot.top + ((m - lo) / (hi - lo || 60)) * (plot.bottom - plot.top);
  const hourStep = HOUR_STEPS.find((s) => (hi - lo) / 60 / s <= (compact ? 6 : 8)) ?? 6;
  const hours: number[] = [];
  for (let m = Math.ceil(lo / (hourStep * 60)) * hourStep * 60; m <= hi; m += hourStep * 60) hours.push(m);

  const ticks = useMemo(() => timeTicks(domain, Math.floor((plot.right - plot.left) / (compact ? 64 : 84))), [domain, plot.left, plot.right, compact]);
  const dayPx = x(domain[0] + DAY) - x(domain[0]);
  const lineW = Math.min(6, Math.max(1, dayPx * 0.45));
  const dotR = Math.min(3.5, Math.max(1.6, dayPx * 0.35));
  const bed = clockSpread(rows.map((r) => r.bed));
  const wake = clockSpread(rows.map((r) => r.wake));
  const at = (m: number) => formatTime(clockIso(m));
  const typical = [bed && { m: bed.median, color: BED, label: t("signals.bedTypical", { time: at(bed.median) }) },
    wake && { m: wake.median, color: WAKE, label: t("signals.bedTypical", { time: at(wake.median) }) }].filter((v) => !!v);
  const summary = bed && wake ? `${t("signals.bedLabel")}. ${t("signals.sumBedtime")}: ${at(bed.median)}, ${t("signals.sumWake")}: ${at(wake.median)}.` : t("signals.bedLabel");
  const totalH = plot.bottom + 26;
  const todayVisible = todayMs >= domain[0] && todayMs <= domain[1];

  return (
    <div className="surface min-w-0 space-y-3 p-4">
      <div ref={ref} className="w-full max-w-full overflow-hidden">
        <svg width={width} height={totalH} role="img" aria-label={summary} className="block font-sans">
          <g aria-hidden>
            {hours.map((m) => (
              <g key={m}>
                <line x1={plot.left} x2={plot.right} y1={y(m)} y2={y(m)} className="stroke-border" strokeOpacity={m % 1440 === 0 ? 1 : 0.6} strokeDasharray={m % 1440 === 0 ? undefined : "2 4"} />
                <text x={plot.left - 8} y={y(m) + 4} textAnchor="end" className={m % 1440 === 0 ? "fill-foreground text-[11px] font-medium tnum" : "fill-muted-foreground text-[11px] tnum"}>{at(m)}</text>
              </g>
            ))}
            <TimeAxis ticks={ticks} x={x} plot={plot} i18n={i18n} />
            {todayVisible && <TodayMarker px={x(todayMs)} plot={plot} label={t("charts.today")} />}
            {!rows.length && <text x={(plot.left + plot.right) / 2} y={(plot.top + plot.bottom) / 2} textAnchor="middle" className="fill-muted-foreground text-[13px]">{t("signals.barsNone")}</text>}
            {rows.map(({ n, bed: b, wake: w }) => {
              const px = x(dayMs(n.wake_date)), sel = n.session_id === selectedId;
              return (
                <g key={n.session_id}>
                  <line x1={px} x2={px} y1={y(shift(b))} y2={y(shift(w))} strokeWidth={sel ? Math.max(3, lineW) : lineW} strokeLinecap="round"
                    style={{ stroke: sel ? "var(--foreground)" : "color-mix(in oklab, var(--chart-1) 30%, var(--card))" }} />
                  <circle cx={px} cy={y(shift(b))} r={sel ? dotR + 1.5 : dotR} style={{ fill: BED }} stroke="var(--card)" strokeWidth={dotR > 2 ? 1 : 0} />
                  <circle cx={px} cy={y(shift(w))} r={sel ? dotR + 1.5 : dotR} style={{ fill: WAKE }} stroke="var(--card)" strokeWidth={dotR > 2 ? 1 : 0} />
                </g>
              );
            })}
            {typical.map((tl) => (
              <g key={tl.color}>
                <line x1={plot.left} x2={plot.right} y1={y(shift(tl.m))} y2={y(shift(tl.m))} strokeWidth={1.5} strokeDasharray="6 4" style={{ stroke: tl.color }} />
                {!compact && <text x={plot.right + 6} y={y(shift(tl.m)) + 4} className="fill-foreground text-[11px] font-medium tnum">{tl.label}</text>}
              </g>
            ))}
          </g>
        </svg>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden>
        <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: BED }} />{t("signals.bedFell")}{compact && bed ? ` · ${t("signals.bedTypical", { time: at(bed.median) })}` : ""}</li>
        <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: WAKE }} />{t("signals.bedWoke")}{compact && wake ? ` · ${t("signals.bedTypical", { time: at(wake.median) })}` : ""}</li>
      </ul>
    </div>
  );
}
