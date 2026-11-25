import type { ClientI18n } from "@/lib/i18n/client-core";
import { DAY } from "./time-scale";

/** "5 days", "7 months", "2 years" — rounded to the unit a reader would use. */
export function durationLabel(i18n: ClientI18n, days: number): string {
  const { tp, formatNumber } = i18n;
  const d = Math.max(0, Math.round(days));
  if (d < 60) return tp("charts.days", d);
  if (d < 730) return tp("charts.months", Math.round(d / 30.44));
  const years = Math.round((d / 365.25) * 10) / 10;
  const whole = Number.isInteger(years);
  return whole ? tp("charts.years", years) : `${formatNumber(years, { maximumFractionDigits: 1 })} ${i18n.t("charts.yearsFraction")}`;
}

export const ageDays = (iso: number, todayMs: number): number => Math.max(0, Math.round((todayMs - iso) / DAY));
