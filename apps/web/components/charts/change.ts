import type { HistoryPoint } from "@/lib/types";

export type Direction = "up" | "down" | "flat";
export type Judgement = "toward" | "away" | "stayed" | "unknown";

export type Change = { abs: number; pct: number | null; direction: Direction; judgement: Judgement };

/** How far a value lies outside [min, max]; 0 when inside or when there is no range. */
export function distanceOutside(value: number, min: number | null, max: number | null): number {
  if (min !== null && value < min) return min - value;
  if (max !== null && value > max) return value - max;
  return 0;
}

const FLAT_PCT = 0.5;

/** Change between two consecutive results, judged against the later result's reference range (or the earlier one's). */
export function classifyChange(a: HistoryPoint, b: HistoryPoint): Change {
  const abs = b.value - a.value;
  const pct = a.value !== 0 ? (abs / Math.abs(a.value)) * 100 : null;
  const direction: Direction = abs === 0 || (pct !== null && Math.abs(pct) < FLAT_PCT) ? "flat" : abs > 0 ? "up" : "down";
  const min = b.ref_min ?? a.ref_min;
  const max = b.ref_max ?? a.ref_max;
  if (min === null && max === null) return { abs, pct, direction, judgement: "unknown" };
  const before = distanceOutside(a.value, min, max);
  const after = distanceOutside(b.value, min, max);
  const judgement: Judgement = before === 0 && after === 0 ? "stayed" : after < before ? "toward" : after > before ? "away" : "stayed";
  return { abs, pct, direction, judgement };
}

/** Signed text with a real minus sign; the caller supplies number formatting. */
export const signOf = (n: number): string => (n > 0 ? "+" : n < 0 ? "−" : "");
export const arrowOf = (d: Direction): string => (d === "up" ? "▲" : d === "down" ? "▼" : "▬");

export type RangeSide = "below" | "within" | "above" | "none";
export function rangeSide(p: HistoryPoint): RangeSide {
  if (p.ref_min === null && p.ref_max === null) return "none";
  if (p.ref_min !== null && p.value < p.ref_min) return "below";
  if (p.ref_max !== null && p.value > p.ref_max) return "above";
  return "within";
}
