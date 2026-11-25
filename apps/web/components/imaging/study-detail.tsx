"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api-error";
import type { ImagingStudy } from "@/lib/types";
import { KeyframeViewer } from "./keyframe-viewer";
import { StudyNotes } from "./study-notes";
import { useI18n } from "@/lib/i18n/client";

type Props = { study: ImagingStudy; onSaved: (study: ImagingStudy) => void; onDeleted: (id: number) => void };

export function StudyDetail({ study, onSaved, onDeleted }: Props) {
  const { t, tp, formatDate } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setDeleting(true); setError(null);
    try {
      const res = await fetch(`/api/imaging/${study.id}`, { method: "DELETE" });
      if (!res.ok) { setError(await errorMessage(res, t("imaging.deleteFailed"))); return; }
      onDeleted(study.id);
    } catch {
      setError(t("imaging.apiUnreachable"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <article className="min-w-0 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-3xl font-semibold">{study.study_type}{study.body_part ? `, ${study.body_part}` : ""}</h2>
          <p className="tnum mt-1 text-sm text-muted-foreground">
            {formatDate(study.study_date)}{study.series_description ? ` · ${study.series_description}` : ""} · {tp("imaging.slicesInLargest", study.slice_count)}
          </p>
        </div>
        {confirming ? (
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("imaging.confirmDelete")}>
            <span className="text-sm">{t("imaging.deleteQuestion")}</span>
            <Button size="sm" variant="destructive" onClick={remove} disabled={deleting}>{deleting ? t("imaging.deleting") : t("imaging.deleteStudy")}</Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>{t("imaging.cancel")}</Button>
          </div>
        ) : <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>{t("imaging.deleteStudy")}</Button>}
      </header>
      {error && <p role="alert" className="rounded-xl border border-outrange/50 p-3 text-sm text-outrange">{error}</p>}
      <KeyframeViewer study={study} />
      <StudyNotes study={study} onSaved={onSaved} />
    </article>
  );
}
