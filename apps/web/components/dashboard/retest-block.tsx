import Link from "next/link";
import { AlertTriangle, ArrowUpRight, Clock } from "lucide-react";
import { ageText } from "@/components/courses/age";
import type { Course, FreshnessItem } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { SectionHeader } from "./section-header";

const MAX_ROWS = 6;

/** Markers whose latest result is older than their re-test guide, or whose course has ended. Hidden when there is nothing to re-test. */
export async function RetestBlock({ items, courses }: { items: FreshnessItem[]; courses: Course[] }) {
  const i18n = await getI18n();
  const { t, formatDate } = i18n;
  const due = items.filter((i) => i.status !== "fresh");
  if (due.length === 0) return null;
  const shown = due.slice(0, MAX_ROWS);
  const byId = new Map(courses.map((c) => [c.id, c]));

  return (
    <section aria-labelledby="retest-h">
      <SectionHeader id="retest-h" title={t("courses.retestTitle")} sub={t("courses.retestSub")} />
      <ul className="surface divide-y overflow-hidden border-l-4 border-l-warn">
        {shown.map((i) => {
          const course = i.reason === "course" && i.course_id !== null ? byId.get(i.course_id) : undefined;
          const Icon = i.status === "overdue" ? AlertTriangle : Clock;
          return (
            <li key={i.marker_key}>
              <Link href={`/biomarkers/${encodeURIComponent(i.marker_key)}`} className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-accent/50">
                <Icon className={`mt-0.5 size-4 shrink-0 ${i.status === "overdue" ? "text-outrange" : "text-warn"}`} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline gap-x-3">
                    <span className="font-medium">{i.display_name}</span>
                    <span className="tnum text-sm text-muted-foreground">{t("courses.measured", { age: ageText(i18n, i.age_days) })}</span>
                    <span className="text-sm text-muted-foreground">· {i.status === "overdue" ? t("courses.statusOverdue") : t("courses.statusDue")} · {i.reason === "course" ? t("courses.whyCourse") : t("courses.whyInterval")}</span>
                  </span>
                  {course?.end_date && <span className="mt-0.5 block text-sm">{t("courses.coursePrompt", { course: course.name, date: formatDate(course.end_date, { day: "numeric", month: "short" }), marker: i.display_name })}</span>}
                </span>
                <ArrowUpRight className="mt-0.5 hidden size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground sm:block" aria-hidden />
              </Link>
            </li>
          );
        })}
        {due.length > MAX_ROWS && (
          <li className="px-4 py-3 text-sm text-muted-foreground"><Link href="/biomarkers" className="underline underline-offset-4">{t("courses.retestMore", { n: due.length - MAX_ROWS })}</Link></li>
        )}
      </ul>
    </section>
  );
}
