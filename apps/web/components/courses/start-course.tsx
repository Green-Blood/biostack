"use client";
import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { COURSES_CHANGED } from "./courses-panel";
import { CourseForm } from "./course-form";

/** Compact "Start a course" button for a marker page; opens the same form with this marker preselected. */
export function StartCourse({ markerKey, markerName }: { markerKey: string; markerName: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <>
      {!open && <Button size="sm" variant="outline" onClick={() => { setOpen(true); setDone(false); }}><Plus aria-hidden />{t("courses.startButton")}</Button>}
      {done && !open && <span role="status" className="text-sm text-muted-foreground">{t("courses.saved")}</span>}
      {open && (
        <div className="surface basis-full p-4 sm:p-5">
          <h2 className="mb-3 text-xl font-semibold">{t("courses.addTitle")}</h2>
          <CourseForm initialMarker={{ marker_key: markerKey, display_name: markerName }}
            onSaved={() => { setOpen(false); setDone(true); window.dispatchEvent(new Event(COURSES_CHANGED)); }} onCancel={() => setOpen(false)} />
        </div>
      )}
    </>
  );
}
