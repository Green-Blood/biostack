"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ImagingStudy, UploadedStudy } from "@/lib/types";
import { StudyDetail } from "./study-detail";
import { StudyRail } from "./study-rail";
import { UploadDialog } from "./upload-dialog";
import { useI18n } from "@/lib/i18n/client";

const newestFirst = (a: ImagingStudy, b: ImagingStudy) => b.study_date.localeCompare(a.study_date) || b.id - a.id;

export function ImagingView({ initial }: { initial: ImagingStudy[] }) {
  const { t } = useI18n();
  const [studies, setStudies] = useState(initial);
  const linked = Number(useSearchParams().get("study")) || null; // deep link from search: ?study=<id>
  const [selectedId, setSelectedId] = useState<number | null>(initial.find((s) => s.id === linked)?.id ?? initial[0]?.id ?? null);
  const [uploading, setUploading] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const selected = studies.find((s) => s.id === selectedId) ?? null;

  function uploaded({ warnings: found, ...study }: UploadedStudy) {
    setStudies((all) => [...all, study].sort(newestFirst));
    setSelectedId(study.id); setWarnings(found); setUploading(false);
  }
  function deleted(id: number) {
    const rest = studies.filter((s) => s.id !== id);
    setStudies(rest); setSelectedId(rest[0]?.id ?? null); setWarnings([]);
  }
  function openExisting(id: number) { setSelectedId(id); setUploading(false); }

  return (
    <div className="space-y-6">
      <div><Button size="lg" onClick={() => setUploading(true)}><Upload aria-hidden /> {t("imaging.uploadStudy")}</Button></div>
      <UploadDialog open={uploading} onClose={() => setUploading(false)} onUploaded={uploaded} onOpenExisting={openExisting} />
      {warnings.length > 0 && (
        <ul role="status" className="space-y-1 rounded-xl border border-warn/60 bg-card p-3 text-sm">
          {warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
      {studies.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">{t("imaging.empty")}</p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <StudyRail studies={studies} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setWarnings([]); }} />
          {selected && <StudyDetail key={selected.id} study={selected} onSaved={(s) => setStudies((all) => all.map((x) => (x.id === s.id ? s : x)).sort(newestFirst))} onDeleted={deleted} />}
        </div>
      )}
    </div>
  );
}
