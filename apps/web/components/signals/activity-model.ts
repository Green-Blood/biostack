import { DAY, dayMs, isoDay, type Domain } from "@/components/charts/time-scale";
import type { SignalPoint, WorkoutItem, WorkoutType } from "@/lib/types";

// Calendar arithmetic runs on UTC day numbers (no DST steps); pixel positions use the charts' local `dayMs`.
const utc = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const isoOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);
/** Monday of the ISO week holding the UTC day `ms`. */
const mondayOf = (ms: number) => ms - ((new Date(ms).getUTCDay() + 6) % 7) * DAY;

export type Week = { from: string; to: string; mid: number; mean: number; days: number };

/** Mean steps per ISO week (Monday first), over the days that have a value; oldest first. `mid` is the week's
 *  middle in ms, where the weekly line puts its point. */
export function weeklyMeans(points: SignalPoint[]): Week[] {
  const weeks = new Map<number, { sum: number; n: number }>();
  for (const p of points) {
    const m = mondayOf(utc(p.date));
    const w = weeks.get(m) ?? { sum: 0, n: 0 };
    w.sum += p.value; w.n += 1;
    weeks.set(m, w);
  }
  return [...weeks.entries()].sort((a, b) => a[0] - b[0])
    .map(([m, w]) => ({ from: isoOf(m), to: isoOf(m + 6 * DAY), mid: dayMs(isoOf(m)) + 3.5 * DAY, mean: w.sum / w.n, days: w.n }));
}

/** The week a date falls in, from a list made by `weeklyMeans`. */
export const weekOf = (weeks: Week[], iso: string): Week | undefined => {
  const from = isoOf(mondayOf(utc(iso)));
  return weeks.find((w) => w.from === from);
};

export type DayLoad = { count: number; minutes: number; types: string[] };

/** Workouts per local date. */
export function workoutsByDay(items: WorkoutItem[]): Map<string, DayLoad> {
  const out = new Map<string, DayLoad>();
  for (const w of items) {
    const d = out.get(w.local_date) ?? { count: 0, minutes: 0, types: [] };
    d.count += 1; d.minutes += w.duration_min;
    if (!d.types.includes(w.type_name)) d.types.push(w.type_name);
    out.set(w.local_date, d);
  }
  return out;
}

/** Type chips for the shown workouts, most frequent first; names come from the API's own list. */
export function typeCounts(items: WorkoutItem[]): WorkoutType[] {
  const map = new Map<number, WorkoutType>();
  for (const w of items) {
    const t = map.get(w.type_code) ?? { type_code: w.type_code, type_name: w.type_name, count: 0 };
    t.count += 1;
    map.set(w.type_code, t);
  }
  return [...map.values()].sort((a, b) => b.count - a.count || a.type_code - b.type_code);
}

export type HeatCell = { date: string; col: number; row: number; load: DayLoad | null; month: boolean };

/**
 * A calendar strip: one column per ISO week, one row per weekday (Monday on top), from the first to the last day of
 * the range (both clipped to whole days). `month` marks the first column of each month, for its label.
 */
export function heatCells(from: string, to: string, byDay: Map<string, DayLoad>): { cells: HeatCell[]; cols: number } {
  const lo = utc(from), hi = utc(to);
  if (!(hi >= lo)) return { cells: [], cols: 0 };
  const start = mondayOf(lo);
  const cells: HeatCell[] = [];
  let lastMonth = "";
  for (let ms = lo; ms <= hi; ms += DAY) {
    const date = isoOf(ms);
    const col = Math.floor((ms - start) / (7 * DAY));
    const row = (new Date(ms).getUTCDay() + 6) % 7;
    const month = date.slice(0, 7) !== lastMonth;
    lastMonth = date.slice(0, 7);
    cells.push({ date, col, row, load: byDay.get(date) ?? null, month });
  }
  return { cells, cols: (cells.at(-1)?.col ?? -1) + 1 };
}

/** Shade step of a day: 0 none, 1 under 30 min, 2 under an hour, 3 an hour or more of workouts. */
export const heatLevel = (load: DayLoad | null): 0 | 1 | 2 | 3 => (!load ? 0 : load.minutes < 30 ? 1 : load.minutes < 60 ? 2 : 3);

/** The visible window as whole days, clipped to the data and today: [from, to] ISO dates. */
export function clipDays(domain: Domain, first: string, today: string): [string, string] {
  const lo = isoDay(domain[0] + DAY - 1), hi = isoDay(domain[1]);
  return [lo > first ? lo : first, hi < today ? hi : today];
}
