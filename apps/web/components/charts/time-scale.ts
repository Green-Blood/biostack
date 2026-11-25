import { parseDay } from "@/lib/i18n/format";

export const DAY = 86_400_000;

/** A calendar day (YYYY-MM-DD) as local-midnight milliseconds. */
export const dayMs = (iso: string): number => parseDay(iso).getTime();

export const isoDay = (ms: number): string => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export type Domain = [number, number];

/** Linear map from time to a pixel range. */
export function timeScale(domain: Domain, x0: number, x1: number): (ms: number) => number {
  const span = domain[1] - domain[0] || DAY;
  return (ms) => x0 + ((ms - domain[0]) / span) * (x1 - x0);
}

export type TimeTick = { ms: number; kind: "year" | "month" | "day" };

const MONTH_STEPS = [1, 2, 3, 6, 12, 24, 60];

/**
 * Ticks at calendar-friendly positions for the visible span: weekly for a few weeks,
 * then months (1, 2, 3, 6), then years. Never more than `maxTicks`.
 * A tick on 1 January is marked as "year" so it can be labelled with the year.
 */
export function timeTicks(domain: Domain, maxTicks: number): TimeTick[] {
  const [lo, hi] = domain;
  const days = (hi - lo) / DAY;
  const limit = Math.max(2, maxTicks);
  if (days <= 75) {
    const step = [7, 14, 28].find((s) => days / s <= limit) ?? 28;
    const out: TimeTick[] = [];
    const start = new Date(lo);
    start.setHours(0, 0, 0, 0);
    for (let t = start.getTime() + DAY; t <= hi; t = new Date(t + step * DAY).setHours(0, 0, 0, 0)) {
      if (t >= lo) out.push({ ms: t, kind: "day" });
    }
    return out;
  }
  const first = new Date(lo);
  const totalMonths = days / 30.4;
  const step = MONTH_STEPS.find((s) => totalMonths / s <= limit) ?? 120;
  const out: TimeTick[] = [];
  let y = first.getFullYear();
  let m = first.getMonth();
  m -= m % step; // align to multiples of the step so ticks sit on Jan, Apr, Jul… not on odd months
  if (step >= 12) m = 0;
  if (step >= 24) y -= y % (step / 12);
  for (let guard = 0; guard < 400; guard++) {
    const t = new Date(y, m, 1).getTime();
    if (t > hi) break;
    if (t >= lo) out.push({ ms: t, kind: m === 0 ? "year" : "month" });
    m += step;
    y += Math.floor(m / 12);
    m %= 12;
  }
  return out;
}

/** "Nice" value ticks covering [lo, hi]: returns the padded domain and the tick values. */
export function niceTicks(lo: number, hi: number, count = 5): { domain: [number, number]; ticks: number[] } {
  if (!(hi > lo)) {
    const pad = Math.abs(lo) * 0.1 || 1;
    lo -= pad;
    hi += pad;
  }
  const raw = (hi - lo) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Math.round(v / step) * step);
  return { domain: [start, end], ticks };
}

/** Whole days between two day-milliseconds (rounded). */
export const daysBetween = (a: number, b: number): number => Math.round((b - a) / DAY);
