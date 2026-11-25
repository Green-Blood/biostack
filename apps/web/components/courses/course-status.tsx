"use client";
import { CalendarClock, CalendarOff, CheckCheck, Pill } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import type { Course } from "@/lib/types";

/** Status chip: icon + words, never colour alone. */
export function CourseChip({ course }: { course: Course }) {
  const { t, tp } = useI18n();
  const cls = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium";
  if (course.status === "undated") return <span className={`${cls} text-muted-foreground`}><CalendarOff className="size-3.5" aria-hidden />{t("courses.statusUndated")}</span>;
  if (course.status === "planned") return <span className={`${cls} text-muted-foreground`}><CalendarClock className="size-3.5" aria-hidden />{t("courses.statusPlanned")}</span>;
  if (course.status === "finished") return <span className={`${cls} text-muted-foreground`}><CheckCheck className="size-3.5" aria-hidden />{t("courses.statusFinished")}</span>;
  const n = course.ends_in_days;
  const tail = n === null ? t("courses.openEnded") : n <= 0 ? t("courses.endsToday") : tp("courses.endsIn", n);
  return <span className={`${cls} border-data/60`}><Pill className="size-3.5" aria-hidden />{t("courses.statusActive")} · {tail}</span>;
}
