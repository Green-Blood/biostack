import type { Period } from "@/components/charts/period";
import type { ChartPoint } from "@/components/charts/time-chart";
import { DAY, dayMs, type Domain } from "@/components/charts/time-scale";
import type { SignalPoint, SignalSeries } from "@/lib/types";

/** The API's "your usual" band: the 25th–75th percentile of the 30 days before the latest day (services/signals.py). */
export const BAND_DAYS = 30;

/** Daily pages open on the last 3 months: a year of days is one click away, and a few months read at a glance. */
export const DAILY_PERIOD: Period = { kind: "3m", from: "", to: "" };

export const HEART_KEYS = ["resting_hr", "hrv_sdnn", "hrv_rmssd", "skin_temp_delta", "spo2_avg", "spo2_min", "respiratory_rate"] as const;
export const ACTIVITY_KEYS = ["steps", "distance_m", "active_kcal"] as const;
export type MetricKey = (typeof HEART_KEYS)[number] | (typeof ACTIVITY_KEYS)[number];

/** How each metric is shown: decimals, sign, and a scale for display (distance is stored in metres, shown in km). */
export const SHOW: Record<MetricKey, { digits: number; signed?: boolean; scale?: number }> = {
  resting_hr: { digits: 0 }, hrv_sdnn: { digits: 0 }, hrv_rmssd: { digits: 0 },
  skin_temp_delta: { digits: 1, signed: true }, spo2_avg: { digits: 1 }, spo2_min: { digits: 0 }, respiratory_rate: { digits: 1 },
  steps: { digits: 0 }, distance_m: { digits: 1, scale: 1 / 1000 }, active_kcal: { digits: 0 },
};

export type NumberFormat = (n: number, o?: Intl.NumberFormatOptions) => string;

/** A value of a metric as text, in its display scale. */
export function metricText(fmt: NumberFormat, key: MetricKey, value: number): string {
  const { digits, signed, scale = 1 } = SHOW[key];
  return fmt(value * scale, { maximumFractionDigits: digits, minimumFractionDigits: signed ? digits : 0, signDisplay: signed ? "exceptZero" : "auto" });
}

/**
 * TimeChart points for a daily series. The usual band is put on the points it describes (the latest day and the 30
 * days before it), so the chart draws it as a range and older days are not judged against today's usual.
 * `notes` adds a tooltip line per date.
 */
export function toChartPoints(s: SignalSeries, key: MetricKey, notes?: Map<string, string>): ChartPoint[] {
  const scale = SHOW[key].scale ?? 1;
  const last = s.points.at(-1);
  const bandFrom = last ? dayMs(last.date) - BAND_DAYS * DAY - DAY / 2 : Infinity; // half a day of slack for DST
  return s.points.map((p) => {
    const banded = s.band !== null && dayMs(p.date) >= bandFrom;
    return {
      date: p.date, value: p.value * scale, unit: s.unit, out_of_range: false, date_suspect: false, is_demo: false,
      ref_min: banded ? s.band!.p25 * scale : null, ref_max: banded ? s.band!.p75 * scale : null, note: notes?.get(p.date) ?? null,
    };
  });
}

/** Points of a series inside the visible window. */
export const pointsIn = <P extends { date: string }>(points: P[], domain: Domain): P[] =>
  points.filter((p) => { const ms = dayMs(p.date); return ms >= domain[0] && ms <= domain[1]; });

/** The first date of any of the given series (for the period selector's lower bound and the events context). */
export function firstDate(series: (SignalSeries | undefined)[]): string | null {
  return series.flatMap((s) => (s?.points[0] ? [s.points[0].date] : [])).sort()[0] ?? null;
}

export const lastPoint = (s: SignalSeries | undefined): SignalPoint | null => s?.points.at(-1) ?? null;

/** Mean of the points dated within the `days` days up to `end` (inclusive), or null when none. */
export function recentMean(points: SignalPoint[], end: string, days: number): { mean: number; n: number } | null {
  const hi = dayMs(end) + DAY / 2, lo = dayMs(end) - (days - 1) * DAY - DAY / 2;
  const xs = points.filter((p) => { const ms = dayMs(p.date); return ms >= lo && ms <= hi; }).map((p) => p.value);
  return xs.length ? { mean: xs.reduce((a, b) => a + b, 0) / xs.length, n: xs.length } : null;
}
