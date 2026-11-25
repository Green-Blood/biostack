import { DAY, dayMs, type Domain } from "./time-scale";

export type PeriodKind = "3m" | "1y" | "all" | "custom";
export type Period = { kind: PeriodKind; from: string; to: string };

export const DEFAULT_PERIOD: Period = { kind: "all", from: "", to: "" };

/** Visible time window for a period. `times` are the result dates in ms; today is always included for "all". */
export function periodDomain(period: Period, times: number[], todayMs: number): Domain {
  if (period.kind === "3m") return [todayMs - 91 * DAY, todayMs + 3 * DAY];
  if (period.kind === "1y") return [todayMs - 365 * DAY, todayMs + 7 * DAY];
  if (period.kind === "custom" && period.from && period.to) {
    const lo = dayMs(period.from), hi = dayMs(period.to);
    if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo) return [lo, hi];
  }
  const lo = times.length ? Math.min(...times) : todayMs - 365 * DAY;
  const hi = Math.max(todayMs, ...times);
  const pad = Math.max((hi - lo) * 0.05, 10 * DAY);
  return [lo - pad, hi + pad];
}

export const inDomain = (ms: number, d: Domain): boolean => ms >= d[0] && ms <= d[1];
