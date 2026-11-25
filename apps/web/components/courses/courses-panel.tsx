"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { Course } from "@/lib/types";
import { CourseChip } from "./course-status";
import { CourseForm } from "./course-form";
import { EffectView } from "./effect-view";
import { byStartDesc, periodText } from "./period";

const order = { active: 0, planned: 1, finished: 2, undated: 3 } as const;
const sortCourses = (all: Course[]) => [...all].sort((a, b) => order[a.status] - order[b.status] || byStartDesc(a, b) || b.id - a.id);

export const COURSES_CHANGED = "biostack:courses-changed";

export function CoursesPanel() {
  const { t, tp, formatDate } = useI18n();
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const load = useCallback(() => {
    getJson<Course[]>("courses").then((c) => { setCourses(sortCourses(c)); setFailed(false); }).catch(() => setFailed(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const changed = () => { setVersion((v) => v + 1); load(); window.dispatchEvent(new Event(COURSES_CHANGED)); };
  async function remove(id: number) {
    setError(null);
    try { await sendJson(`courses/${id}`, "DELETE"); setConfirming(null); changed(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <section aria-labelledby="courses-title" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-prose">
          <h2 id="courses-title" className="font-semibold">{t("courses.sectionTitle")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("courses.sectionIntro")}</p>
        </div>
        {!adding && <Button size="lg" onClick={() => setAdding(true)}><Plus aria-hidden />{t("courses.addTitle")}</Button>}
      </div>
      {adding && (
        <div className="surface p-4 sm:p-5">
          <h3 className="mb-3 font-semibold">{t("courses.addTitle")}</h3>
          <CourseForm onSaved={() => { setAdding(false); changed(); }} onCancel={() => setAdding(false)} />
        </div>
      )}
      {failed && <p role="alert" className="text-sm text-outrange">{t("courses.loadFailed")}</p>}
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
      {courses && courses.length === 0 && !adding && <p className="empty-state p-6 text-muted-foreground">{t("courses.empty")}</p>}
      {courses && courses.length > 0 && (
        <ul className="space-y-3">
          {courses.map((c) => (
            <li key={c.id} className="surface p-4">
              {editing === c.id ? (
                <CourseForm course={c} onSaved={() => { setEditing(null); changed(); }} onCancel={() => setEditing(null)} />
              ) : (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    <h3 className="font-semibold">{c.name}{c.dosage && <span className="ml-2 font-normal text-muted-foreground">{c.dosage}</span>}</h3>
                    <CourseChip course={c} />
                  </div>
                  <p className="tnum text-sm text-muted-foreground">
                    {periodText(t, formatDate, c)}
                    {c.days !== null && <> · {tp("courses.daysCount", c.days)}</>}
                  </p>
                  {c.target_marker_key && (
                    <p className="text-sm">
                      <Link href={`/biomarkers/${encodeURIComponent(c.target_marker_key)}`} className="underline underline-offset-4">{t("courses.target", { name: c.target_marker_name ?? c.target_marker_key })}</Link>
                    </p>
                  )}
                  {c.notes && <p className="whitespace-pre-line text-sm text-muted-foreground">{c.notes}</p>}
                  {c.status === "finished" && c.target_marker_key && (
                    <div className="rounded-2xl border bg-muted/40 p-3"><EffectView courseId={c.id} markerKey={c.target_marker_key} refreshKey={version} /></div>
                  )}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <Button size="sm" variant="outline" onClick={() => { setEditing(c.id); setConfirming(null); }}><Pencil aria-hidden />{t("courses.edit")}</Button>
                    {c.editable && (confirming === c.id ? (
                      <span role="group" aria-label={t("courses.confirmDelete")} className="flex items-center gap-2 text-sm">
                        {t("courses.confirmDelete")}
                        <Button size="sm" variant="destructive" onClick={() => remove(c.id)}>{t("courses.confirmYes")}</Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>{t("courses.confirmNo")}</Button>
                      </span>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => setConfirming(c.id)}><Trash2 aria-hidden />{t("courses.remove")}</Button>
                    ))}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t("courses.caveat")}</p>
    </section>
  );
}
