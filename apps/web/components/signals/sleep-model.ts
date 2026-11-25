import type { Key } from "@/lib/i18n/translate";
import type { SleepNight, SleepStageName, SleepStageSpan } from "@/lib/types";

// Calm categorical colours from the theme: deep = the data colour, light = a tint of it, REM = a second hue, awake =
// neutral grey; the tints are theme tokens (globals.css) that keep >= 3:1 against the card. No red/green: a stage is not good or bad. `level` is the hypnogram row (0 = top).
export const STAGES: { key: SleepStageName; label: Key; color: string; level: number }[] = [
  { key: "deep", label: "signals.stageDeep", color: "var(--chart-1)", level: 3 },
  { key: "rem", label: "signals.stageRem", color: "var(--chart-4)", level: 1 },
  { key: "light", label: "signals.stageLight", color: "var(--stage-light)", level: 2 },
  { key: "awake", label: "signals.stageAwake", color: "var(--stage-awake)", level: 0 },
];
export const STAGE: Record<SleepStageName, (typeof STAGES)[number]> = Object.fromEntries(STAGES.map((s) => [s.key, s])) as never;

const DAY_MIN = 1440;

// ---- naive local times ----

/** Minutes since 1970 of a naive local ISO string ("2026-11-11T23:10:00"), read as written (no zone conversion). */
export function naiveMin(iso: string): number {
  const [y, mo, d] = iso.slice(0, 10).split("-").map(Number);
  const h = Number(iso.slice(11, 13) || 0), mi = Number(iso.slice(14, 16) || 0);
  return Date.UTC(y, mo - 1, d, h, mi) / 60_000;
}

/** Minutes after midnight of a naive local ISO string. */
export const clockOf = (iso: string): number => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));

/** A naive ISO string for a clock time (any minute count, wrapped into one day), for `formatTime`. */
export function clockIso(minutes: number): string {
  const m = ((Math.round(minutes) % DAY_MIN) + DAY_MIN) % DAY_MIN;
  return `2000-01-01T${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}:00`;
}

// ---- clock times that wrap around midnight ----

/** Unwraps clock minutes onto one continuous line by cutting the day at the widest gap between the values, so
 *  23:40 and 00:20 sit 40 minutes apart (00:20 becomes 24:20). Returns the mapping to apply to every value. */
export function clockCut(values: number[]): (minutes: number) => number {
  if (!values.length) return (v) => v;
  const s = [...values].sort((a, b) => a - b);
  let cut = s[0], widest = s[0] + DAY_MIN - s.at(-1)!;
  for (let i = 1; i < s.length; i++) {
    if (s[i] - s[i - 1] > widest) { widest = s[i] - s[i - 1]; cut = s[i]; }
  }
  return (v) => (v < cut ? v + DAY_MIN : v);
}

export function percentile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Middle and middle-half of clock times, handling the wrap at midnight. Results are minutes after midnight. */
export function clockSpread(values: number[]): { median: number; p25: number; p75: number } | null {
  if (!values.length) return null;
  const shift = clockCut(values);
  const s = values.map(shift).sort((a, b) => a - b);
  const wrap = (v: number) => Math.round(v) % DAY_MIN;
  return { median: wrap(percentile(s, 0.5)), p25: wrap(percentile(s, 0.25)), p75: wrap(percentile(s, 0.75)) };
}

// ---- bars: nights grouped by week or month ----

export type Grouping = "night" | "week" | "month";
export const AUTO_WEEKLY_ABOVE = 120;
export type StageAverages = { duration_min: number; deep: number; rem: number; light: number; awake: number };
/** `staged` = how many of the slot's nights have stage data; the stage averages are over those nights only, the
 *  duration average over all of them. */
export type Slot = { key: string; from: string; to: string; nights: SleepNight[]; staged: number; avg: StageAverages };

/** A night with a duration but no stage minutes at all: the API reports 0 for each stage when the watch staged nothing,
 *  so those zeros mean "unknown", not "no deep sleep". */
export const isStaged = (n: SleepNight): boolean => n.deep + n.rem + n.light + n.awake > 0;

const dayNum = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86_400_000;
const isoOf = (n: number) => new Date(n * 86_400_000).toISOString().slice(0, 10);

function slotRange(iso: string, g: Grouping): [string, string] {
  if (g === "night") return [iso, iso];
  if (g === "month") {
    const y = +iso.slice(0, 4), m = +iso.slice(5, 7);
    return [`${iso.slice(0, 7)}-01`, isoOf(Date.UTC(y, m, 0) / 86_400_000)];
  }
  const n = dayNum(iso), monday = n - ((new Date(n * 86_400_000).getUTCDay() + 6) % 7);
  return [isoOf(monday), isoOf(monday + 6)];
}

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

/** Nights (any order) as one slot per night, ISO week (Monday first) or calendar month, oldest first, with averages. */
export function groupNights(nights: SleepNight[], g: Grouping): Slot[] {
  const map = new Map<string, Slot>();
  for (const n of [...nights].sort((a, b) => a.wake_date.localeCompare(b.wake_date))) {
    const [from, to] = slotRange(n.wake_date, g);
    const slot = map.get(from) ?? { key: from, from, to, nights: [], staged: 0, avg: { duration_min: 0, deep: 0, rem: 0, light: 0, awake: 0 } };
    slot.nights.push(n);
    map.set(from, slot);
  }
  return [...map.values()].map((s) => {
    const st = s.nights.filter(isStaged);
    return {
      ...s,
      staged: st.length,
      avg: {
        duration_min: mean(s.nights.map((n) => n.duration_min)), deep: mean(st.map((n) => n.deep)),
        rem: mean(st.map((n) => n.rem)), light: mean(st.map((n) => n.light)), awake: mean(st.map((n) => n.awake)),
      },
    };
  });
}

/** Night bars when there are few enough to read one by one, weekly averages otherwise. */
export const autoGrouping = (count: number): Grouping => (count > AUTO_WEEKLY_ABOVE ? "week" : "night");

/** Days a slot covers, for its width on the time axis. */
export const slotDays = (s: Slot): number => dayNum(s.to) - dayNum(s.from) + 1;

// ---- hypnogram ----

export type HypSegment = { stage: SleepStageName; x0: number; x1: number };
export type Hypnogram = { span: number; segments: HypSegment[]; links: { x: number; from: number; to: number }[]; hours: { x: number; clock: number }[] };

/** Stage spans as minutes from the night's start, the vertical links between touching spans (a gap of a minute or
 *  less counts as touching) and every full hour in the night. Gaps (between recorded parts) stay empty. */
export function hypnogram(stages: SleepStageSpan[], startIso: string, endIso: string): Hypnogram {
  const spans = stages.map((s) => ({ stage: s.stage, a: naiveMin(s.start_local), b: naiveMin(s.end_local) })).filter((s) => s.b > s.a);
  const start = Math.min(naiveMin(startIso), ...spans.map((s) => s.a));
  const end = Math.max(naiveMin(endIso), ...spans.map((s) => s.b));
  const segments = spans.sort((p, q) => p.a - q.a).map((s) => ({ stage: s.stage, x0: s.a - start, x1: s.b - start }));
  const links = segments.slice(1).flatMap((s, i) => {
    const prev = segments[i];
    return s.x0 - prev.x1 <= 1 && s.stage !== prev.stage ? [{ x: s.x0, from: STAGE[prev.stage].level, to: STAGE[s.stage].level }] : [];
  });
  const hours: Hypnogram["hours"] = [];
  for (let m = Math.ceil(start / 60) * 60; m <= end; m += 60) hours.push({ x: m - start, clock: ((m % DAY_MIN) + DAY_MIN) % DAY_MIN });
  return { span: Math.max(end - start, 1), segments, links, hours };
}
