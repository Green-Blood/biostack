"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CircleCheck, Clock, Flag, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { RecordDetail } from "@/lib/types";
import { ConfirmDelete } from "./confirm-delete";
import { ErrorLine, Field, inputClass, useAction } from "./kit";
import { isOngoing, KIND_META, kindOf, spanLabel } from "./meta";

export function RecordHeader({ rec, reload }: { rec: RecordDetail; reload: () => Promise<void> }) {
  const router = useRouter();
  const i18n = useI18n();
  const { t } = i18n;
  const { busy, error, setError, run } = useAction(reload);
  const [mode, setMode] = useState<"edit" | "finish" | null>(null);
  const [f, setF] = useState({ title: "", date: "", end: "", clinic: "", department: "", doctor: "", reason: "" });
  const [finishDate, setFinishDate] = useState(todayIso());
  const kind = kindOf(rec.record_type);
  const { Icon, label } = KIND_META[kind];
  const ongoing = isOngoing(rec);
  const status = rec.status ?? (ongoing ? "ongoing" : rec.end_date ? "completed" : null);
  const where = [rec.clinic, rec.department, rec.doctor_name].filter(Boolean);
  const stay = kind === "hospital_stay";

  function startEdit() {
    setF({ title: rec.title, date: rec.date ?? "", end: rec.end_date ?? "", clinic: rec.clinic ?? "", department: rec.department ?? "", doctor: rec.doctor_name ?? "", reason: rec.reason ?? "" });
    setError(null); setMode("edit");
  }
  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!f.title.trim()) { setError(t("records.needTitle")); return; }
    if (f.date && f.end && f.end < f.date) { setError(t("records.endBeforeStart")); return; }
    const ok = await run(() => sendJson(`records/${rec.id}`, "PATCH", {
      title: f.title.trim(), date: f.date || null, end_date: f.end || null, clinic_name: f.clinic.trim(), department: f.department.trim(), doctor_name: f.doctor.trim(), reason: f.reason.trim(),
      ...(stay ? { status: f.end ? "completed" : "ongoing" } : {}),
    }));
    if (ok) setMode(null);
  }
  async function finish() {
    if (rec.date && finishDate < rec.date) { setError(t("records.endBeforeStart")); return; }
    if (await run(() => sendJson(`records/${rec.id}/finish`, "POST", { end_date: finishDate }))) setMode(null);
  }
  async function remove() {
    try { await sendJson(`records/${rec.id}`, "DELETE"); router.push("/timeline"); router.refresh(); }
    catch (e) { setError((e as Error).message); }
  }

  return (
    <header className="space-y-4">
      <Link href="/timeline" className="inline-flex min-h-11 items-center gap-1.5 rounded-full text-sm font-medium text-primary outline-none underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"><ArrowLeft className="size-4" aria-hidden />{t("records.backToTimeline")}</Link>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-secondary px-3 text-xs font-medium text-secondary-foreground"><Icon className="size-3.5" aria-hidden />{t(label)}</span>
        {status && (
          <span className="inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-xs font-medium">
            {status === "ongoing" ? <Clock className="size-3.5" aria-hidden /> : <CircleCheck className="size-3.5" aria-hidden />}
            {status === "ongoing" ? t("records.statusOngoing") : t("records.statusCompleted")}
          </span>
        )}
      </div>
      <h1 className="break-words font-semibold">{rec.title}</h1>
      <p className="tnum text-base text-muted-foreground">{spanLabel(rec, i18n)}</p>
      {where.length > 0 && <p className="break-words">{where.join(" · ")}</p>}
      {rec.reason && <p className="max-w-prose whitespace-pre-line break-words text-muted-foreground">{rec.reason}</p>}
      {!rec.is_manual && <p className="text-sm text-muted-foreground">{t("records.importedNote")}</p>}

      {mode === null && (
        <div className="flex flex-wrap gap-2">
          {ongoing && rec.is_manual && <Button type="button" size="lg" onClick={() => { setFinishDate(todayIso()); setError(null); setMode("finish"); }}><Flag aria-hidden />{t("records.finishStay")}</Button>}
          {rec.is_manual && <Button type="button" size="lg" variant="outline" onClick={startEdit}><Pencil aria-hidden />{t("records.edit")}</Button>}
          {rec.is_manual && <ConfirmDelete iconOnly={false} label={t("records.deleteRecord")} question={t("records.confirmRecord")} onConfirm={remove} />}
        </div>
      )}
      {mode === "finish" && (
        <div className="surface space-y-3 p-4">
          <Field label={t("records.finishDate")} hint={t("records.finishHint")}>{(id) => <Input id={id} type="date" className={inputClass} value={finishDate} min={rec.date ?? undefined} onChange={(e) => setFinishDate(e.target.value)} autoFocus />}</Field>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="lg" disabled={busy || !finishDate} onClick={finish}>{busy ? t("records.saving") : t("records.finishStay")}</Button>
            <Button type="button" size="lg" variant="outline" onClick={() => setMode(null)}>{t("records.cancel")}</Button>
          </div>
        </div>
      )}
      {mode === "edit" && (
        <form onSubmit={saveEdit} className="surface space-y-4 p-4" aria-label={t("records.edit")}>
          <Field label={t("records.fTitle")}>{(id) => <Input id={id} className={inputClass} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} autoFocus />}</Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={stay ? t("records.fStarted") : t("records.fDate")}>{(id) => <Input id={id} type="date" className={inputClass} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />}</Field>
            <Field label={t("records.fEnded")} hint={stay ? t("records.endEmptyHint") : undefined}>{(id) => <Input id={id} type="date" className={inputClass} value={f.end} min={f.date || undefined} onChange={(e) => setF({ ...f, end: e.target.value })} />}</Field>
            <Field label={stay ? t("records.fHospital") : t("records.fClinic")}>{(id) => <Input id={id} className={inputClass} value={f.clinic} onChange={(e) => setF({ ...f, clinic: e.target.value })} />}</Field>
            <Field label={t("records.fDepartment")}>{(id) => <Input id={id} className={inputClass} value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} />}</Field>
            <Field label={t("records.fDoctor")} className="sm:col-span-2">{(id) => <Input id={id} className={inputClass} value={f.doctor} onChange={(e) => setF({ ...f, doctor: e.target.value })} />}</Field>
          </div>
          <Field label={t("records.fReason")}>{(id) => <Textarea id={id} rows={3} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />}</Field>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="lg" disabled={busy}>{busy ? t("records.saving") : t("records.save")}</Button>
            <Button type="button" size="lg" variant="outline" onClick={() => setMode(null)}>{t("records.cancel")}</Button>
          </div>
        </form>
      )}
      <ErrorLine message={error} />
    </header>
  );
}
