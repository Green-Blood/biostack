import type { Course } from "@/lib/types";
import type { T } from "@/lib/i18n/translate";

/** The dates of a course in words; imported medicines may have only one date or none at all. */
export function periodText(t: T, formatDate: (iso: string) => string, c: Pick<Course, "start_date" | "end_date">): string {
  if (c.start_date && c.end_date) return t("courses.period", { start: formatDate(c.start_date), end: formatDate(c.end_date) });
  if (c.start_date) return t("courses.periodOpen", { start: formatDate(c.start_date) });
  if (c.end_date) return t("courses.periodUntil", { end: formatDate(c.end_date) });
  return t("courses.noDates");
}

export const byStartDesc = (a: Pick<Course, "start_date">, b: Pick<Course, "start_date">): number => (b.start_date ?? "").localeCompare(a.start_date ?? "");
