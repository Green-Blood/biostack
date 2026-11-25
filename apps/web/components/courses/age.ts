import type { T, TPlural } from "@/lib/i18n/translate";

type Say = { t: T; tp: TPlural };

/** "today", "12 days ago", "7 months ago", "2 years ago" from an age in days. */
export function ageText({ t, tp }: Say, days: number): string {
  if (days < 1) return t("courses.ageToday");
  if (days < 60) return tp("courses.ageDays", Math.round(days));
  if (days < 730) return tp("courses.ageMonths", Math.round(days / 30.4));
  return tp("courses.ageYears", Math.round(days / 365.25));
}

/** "about every 3 months" (whole months when the interval is a clean multiple of ~30 days, otherwise days). */
export function intervalText({ t, tp }: Say, days: number | null): string {
  if (days === null) return t("courses.intervalNone");
  if (days >= 60 && Math.abs(days / 30 - Math.round(days / 30)) < 0.06) return tp("courses.intervalMonths", Math.round(days / 30));
  return tp("courses.intervalDays", days);
}
