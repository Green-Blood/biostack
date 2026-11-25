"use client";
import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import { getJson } from "@/lib/request";
import type { Course } from "@/lib/types";
import { CourseChip } from "./course-status";
import { COURSES_CHANGED } from "./courses-panel";
import { EffectView } from "./effect-view";
import { byStartDesc, periodText } from "./period";

/** "Courses and effect" card on the marker page: courses set to check this marker with before/after, plus other courses in the period. */
export function MarkerCourses({ markerKey, from, today }: { markerKey: string; from: string; today: string }) {
  const { t, tp, formatDate } = useI18n();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const load = useCallback(() => {
    getJson<Course[]>("courses").then((c) => { setCourses(c); setFailed(false); setVersion((v) => v + 1); }).catch(() => setFailed(true));
  }, []);
  useEffect(() => {
    load();
    window.addEventListener(COURSES_CHANGED, load);
    return () => window.removeEventListener(COURSES_CHANGED, load);
  }, [load]);

  const mine = (courses ?? []).filter((c) => c.target_marker_key === markerKey).sort(byStartDesc);
  const others = (courses ?? []).filter((c) => c.target_marker_key !== markerKey && c.start_date !== null && c.start_date <= today && (c.end_date === null || c.end_date >= from)).sort(byStartDesc);
  const period = (c: Course) => periodText(t, formatDate, c);

  return (
    <section aria-labelledby="mc-h" className="surface space-y-4 p-4 sm:p-5">
      <div>
        <h2 id="mc-h" className="text-2xl">{t("courses.effectTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("courses.effectIntro")}</p>
      </div>
      {failed && <p role="alert" className="text-sm text-muted-foreground">{t("courses.loadFailed")}</p>}
      {courses && mine.length === 0 && <p className="text-sm text-muted-foreground">{t("courses.effectNone")}</p>}
      {mine.length > 0 && (
        <ul className="space-y-3">
          {mine.map((c) => (
            <li key={c.id} id={`course-${c.id}`} className="scroll-mt-20 rounded-2xl border p-3 target:ring-3 target:ring-ring/50">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <h3 className="font-semibold">{c.name}{c.dosage && <span className="ml-2 font-normal text-muted-foreground">{c.dosage}</span>}</h3>
                <CourseChip course={c} />
              </div>
              <p className="tnum mb-2 mt-1 text-sm text-muted-foreground">{period(c)}{c.days !== null && <> · {tp("courses.daysCount", c.days)}</>}</p>
              <EffectView courseId={c.id} markerKey={markerKey} refreshKey={version} />
            </li>
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <div>
          <h3 className="eyebrow mb-2">{t("courses.otherCourses")}</h3>
          <ul className="space-y-1.5 text-sm">
            {others.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1"><span className="font-medium">{c.name}</span><CourseChip course={c} /><span className="tnum text-muted-foreground">{period(c)}</span></li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{t("courses.caveat")}</p>
    </section>
  );
}
