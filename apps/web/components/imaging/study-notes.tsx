"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api-error";
import type { ImagingStudy } from "@/lib/types";
import { ReportReader } from "./report-reader";
import { useI18n } from "@/lib/i18n/client";

type Props = { study: ImagingStudy; onSaved: (study: ImagingStudy) => void };

export function StudyNotes({ study, onSaved }: Props) {
  const { t } = useI18n();
  const [form, setForm] = useState({
    study_date: study.study_date, study_type: study.study_type, body_part: study.body_part,
    summary_text: study.summary_text, findings_text: study.findings_text,
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const set = (patch: Partial<typeof form>) => { setForm({ ...form, ...patch }); setMessage(null); };

  async function save() {
    if (!form.study_date || !form.study_type.trim()) { setMessage({ text: t("imaging.needDateType"), ok: false }); return; }
    setSaving(true); setMessage(null);
    try {
      const res = await fetch(`/api/imaging/${study.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      if (!res.ok) { setMessage({ text: await errorMessage(res, t("imaging.notesSaveFailed")), ok: false }); return; }
      onSaved((await res.json()) as ImagingStudy);
      setMessage({ text: t("imaging.notesSaved"), ok: true });
    } catch {
      setMessage({ text: t("imaging.apiUnreachable"), ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label={t("imaging.studyNotes")} className="space-y-5">
      <ReportReader studyId={study.id} onDraft={(d) => set({ summary_text: d.summary_text, findings_text: d.findings_text })} />
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.studyDate")}</span>
          <Input type="date" value={form.study_date} onChange={(e) => set({ study_date: e.target.value })} className="tnum" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.type")}</span>
          <Input value={form.study_type} onChange={(e) => set({ study_type: e.target.value })} autoComplete="off" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.bodyPart")}</span>
          <Input value={form.body_part} onChange={(e) => set({ body_part: e.target.value })} autoComplete="off" /></label>
      </div>
      <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.summary")}</span>
        <Textarea value={form.summary_text} onChange={(e) => set({ summary_text: e.target.value })} placeholder={t("imaging.summaryPlaceholder")} /></label>
      <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.findings")}</span>
        <Textarea value={form.findings_text} onChange={(e) => set({ findings_text: e.target.value })} rows={5} placeholder={t("imaging.findingsPlaceholder")} /></label>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={save} disabled={saving}>{saving ? t("imaging.savingNotes") : t("imaging.saveNotes")}</Button>
        <p aria-live="polite" role={message?.ok === false ? "alert" : "status"} className={`text-sm ${message?.ok === false ? "text-outrange" : "text-muted-foreground"}`}>{message?.text}</p>
      </div>
    </section>
  );
}
