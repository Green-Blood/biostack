"use client";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { useI18n } from "@/lib/i18n/client";
import { heatCells, heatLevel, type DayLoad } from "./activity-model";
import { duration } from "./format";

const MIN_CELL = 12;
const MAX_CELL = 22;
const GAP = 3;
const TOP = 18;
const LEFT_W = 28;
// No data colour judges a day: more workout time is just a deeper tint of the same hue.
const SHADE = ["var(--muted)", "color-mix(in oklab, var(--chart-1) 35%, var(--card))", "color-mix(in oklab, var(--chart-1) 65%, var(--card))", "var(--chart-1)"];
const LEVEL_KEYS = ["activity.heatNone", "activity.heatShort", "activity.heatMid", "activity.heatLong"] as const;

type Props = { from: string; to: string; byDay: Map<string, DayLoad> };

/** A calendar heat-strip: one column per week, one cell per day, shaded by that day's workout time. */
export function WorkoutStrip({ from, to, byDay }: Props) {
  const i18n = useI18n();
  const { t, tp, formatDate } = i18n;
  const { cells, cols } = useMemo(() => heatCells(from, to, byDay), [from, to, byDay]);
  const scroller = useRef<HTMLDivElement | null>(null);
  const [measure, width] = useChartWidth();
  const setScroller = useCallback((el: HTMLDivElement | null) => { scroller.current = el; measure(el); if (el) el.scrollLeft = el.scrollWidth; }, [measure]);
  useEffect(() => { const el = scroller.current; if (el) el.scrollLeft = el.scrollWidth; }, [cols, width]);

  // A short period gets bigger cells (up to MAX_CELL) so it fills the card; a long one scrolls at MIN_CELL.
  const CELL = Math.max(MIN_CELL, Math.min(MAX_CELL, Math.floor(width / Math.max(cols, 1)) - GAP));
  const w = cols * (CELL + GAP);
  const h = TOP + 7 * (CELL + GAP);
  const activeDays = cells.filter((c) => c.load).length;
  const total = cells.reduce((a, c) => a + (c.load?.count ?? 0), 0);
  const cellTitle = (date: string, load: DayLoad | null) => `${formatDate(date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}: ${
    load ? `${tp("activity.workoutsN", load.count)}, ${duration(i18n, load.minutes).long} (${load.types.join(", ")})` : t("activity.heatNone")}`;
  const weekday = (row: number) => formatDate(`2024-01-0${row + 1}`, { weekday: "short" }); // 2024-01-01 was a Monday

  return (
    <div className="surface min-w-0 space-y-3 p-4">
      <p className="text-sm text-muted-foreground">
        {cells.length ? t("activity.heatSummary", { workouts: tp("activity.workoutsN", total), days: tp("activity.daysN", activeDays) }) : t("activity.heatEmpty")}
      </p>
      {cells.length > 0 && (
        <div className="flex">
          <svg width={LEFT_W} height={h} aria-hidden className="shrink-0 font-sans">
            {[0, 2, 4].map((r) => (
              <text key={r} x={0} y={TOP + r * (CELL + GAP) + CELL - 2} className="fill-muted-foreground text-[10px]">{weekday(r)}</text>
            ))}
          </svg>
          <div ref={setScroller} className="min-w-0 flex-1 overflow-x-auto overflow-y-hidden overscroll-x-contain">
            <svg width={w} height={h} role="img" aria-label={t("activity.heatLabel", { from: formatDate(from), to: formatDate(to), workouts: tp("activity.workoutsN", total), days: tp("activity.daysN", activeDays) })} className="block font-sans">
              {cells.filter((c) => c.month).map((c) => (
                <text key={`m${c.date}`} x={c.col * (CELL + GAP)} y={11} className="fill-muted-foreground text-[10px]">
                  {formatDate(c.date, c.date.slice(5, 7) === "01" || c.col === 0 ? { month: "short", year: "numeric" } : { month: "short" })}
                </text>
              ))}
              {cells.map((c) => (
                <rect key={c.date} x={c.col * (CELL + GAP)} y={TOP + c.row * (CELL + GAP)} width={CELL} height={CELL} rx={2.5}
                  style={{ fill: SHADE[heatLevel(c.load)] }} className={c.load ? "" : "stroke-border"} strokeWidth={c.load ? 0 : 0.5}>
                  <title>{cellTitle(c.date, c.load)}</title>
                </rect>
              ))}
            </svg>
          </div>
        </div>
      )}
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-hidden>
        {SHADE.map((fill, i) => (
          <li key={fill} className="flex items-center gap-1.5"><span className="size-3 rounded-[3px] border border-border/60" style={{ background: fill }} />{t(LEVEL_KEYS[i])}</li>
        ))}
      </ul>
    </div>
  );
}
