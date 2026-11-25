"use client";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { sendJson } from "@/lib/request";
import type { RecordDetail, RecordInput, RecordKind } from "@/lib/types";
import { DiagnosisFields, dxBody, emptyDx, emptyTx, TreatmentFields, txBody, type DxDraft, type TxDraft } from "./fields";
import { Chip, ErrorLine, Field, inputClass } from "./kit";
import { KIND_META } from "./meta";

type Draft = {
  type: RecordKind | null; title: string; titleTouched: boolean; date: string; ongoing: boolean; endDate: string;
  clinic: string; department: string; doctor: string; reason: string; details: string;
  dx: DxDraft[]; tx: TxDraft[]; questions: { key: number; text: string }[];
};
const DRAFT_KEY = "biostack.recordDraft.v1";

// Step 1 offers five cards; "tests or scans" stands for the lab and imaging types.
const CARDS: { kind: RecordKind; label: Key; hint: Key }[] = [
  { kind: "visit", label: "records.cardVisit", hint: "records.cardVisitHint" },
  { kind: "hospital_stay", label: "records.cardStay", hint: "records.cardStayHint" },
  { kind: "procedure", label: "records.cardProcedure", hint: "records.cardProcedureHint" },
  { kind: "lab", label: "records.cardTests", hint: "records.cardTestsHint" },
  { kind: "other", label: "records.cardOther", hint: "records.cardOtherHint" },
];
const SUGGEST: Record<RecordKind, Key> = {
  visit: "records.titleVisit", hospital_stay: "records.titleStay", procedure: "records.titleProcedure", lab: "records.titleLab", imaging: "records.titleImaging", other: "records.titleOther",
};

const fresh = (): Draft => ({
  type: null, title: "", titleTouched: false, date: todayIso(), ongoing: true, endDate: "", clinic: "", department: "", doctor: "", reason: "", details: "", dx: [], tx: [], questions: [],
});

function hasContent(d: Draft): boolean {
  return d.titleTouched || d.clinic.trim() !== "" || d.department.trim() !== "" || d.doctor.trim() !== "" || d.reason.trim() !== "" || d.details.trim() !== "" || d.endDate !== "" ||
    d.dx.some((x) => x.name.trim()) || d.tx.some((x) => x.name.trim()) || d.questions.some((q) => q.text.trim());
}

export function NewRecord({ clinics }: { clinics: string[] }) {
  const router = useRouter();
  const { t } = useI18n();
  const [d, setD] = useState<Draft>(fresh);
  const [restored, setRestored] = useState(false);
  const [ready, setReady] = useState(false); // true once the stored draft has been looked at
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleBad, setTitleBad] = useState(false);
  const seq = useRef(1);
  const leaving = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const clinicList = useId();
  const key = () => seq.current++;
  const patch = (p: Partial<Draft>) => setD((cur) => ({ ...cur, ...p }));

  // Bring back an unsaved draft from an earlier visit to this page (a closed tab, a dropped connection).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reading browser storage is only possible after mount
      setReady(true);
      if (!raw) return;
      const saved = JSON.parse(raw) as Draft;
      if (!saved || typeof saved !== "object" || !saved.type) return;
      const keys = [...saved.dx, ...saved.tx, ...saved.questions].map((r) => r.key);
      seq.current = Math.max(1, ...keys) + 1;
      setD({ ...fresh(), ...saved }); setRestored(true);
    } catch { /* no storage or a broken draft: start fresh */ }
  }, []);

  const dirty = hasContent(d);
  useEffect(() => {
    if (!ready) return;
    try {
      if (dirty && !leaving.current) localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
      else if (!dirty) localStorage.removeItem(DRAFT_KEY);
    } catch { /* storage is a convenience only */ }
  }, [d, dirty, ready]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { if (!leaving.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function pick(kind: RecordKind) {
    setD((cur) => ({ ...cur, type: kind, title: cur.titleTouched ? cur.title : t(SUGGEST[kind]) }));
    window.scrollTo({ top: 0 });
  }
  function startOver() {
    try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
    setD(fresh()); setRestored(false); setError(null);
  }

  const isStay = d.type === "hospital_stay";
  const card = d.type === "lab" || d.type === "imaging" ? "lab" : d.type;
  const cardLabel = useMemo(() => CARDS.find((c) => c.kind === card), [card]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!d.type) return;
    if (!d.title.trim()) { setTitleBad(true); setError(t("records.needTitle")); titleRef.current?.focus(); return; }
    if (isStay && !d.ongoing && d.endDate && d.date && d.endDate < d.date) { setError(t("records.endBeforeStart")); return; }
    const opt = (s: string) => s.trim() || undefined;
    const body: RecordInput = {
      record_type: d.type, title: d.title.trim(), date: d.date || undefined,
      ...(isStay ? (d.ongoing || !d.endDate ? { status: "ongoing" as const } : { end_date: d.endDate, status: "completed" as const }) : {}),
      clinic_name: opt(d.clinic), department: opt(d.department), doctor_name: opt(d.doctor), reason: opt(d.reason), details: opt(d.details),
      diagnoses: d.dx.filter((x) => x.name.trim()).map(dxBody),
      treatments: d.tx.filter((x) => x.name.trim()).map(txBody),
      questions: d.questions.map((q) => q.text.trim()).filter(Boolean),
    };
    setSaving(true); setError(null); setTitleBad(false);
    try {
      const saved = await sendJson<RecordDetail>("records", "POST", body);
      leaving.current = true;
      try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
      router.push(`/records/${saved.id}`);
    } catch (err) {
      setError(`${(err as Error).message} ${t("records.draftKept")}`);
      setSaving(false);
    }
  }

  if (!d.type) {
    return (
      <div className="space-y-5">
        {restored && <p role="status" className="surface px-4 py-3 text-sm">{t("records.draftRestored")}</p>}
        <p className="text-muted-foreground">{t("records.pickType")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {CARDS.map((c) => {
            const Icon = KIND_META[c.kind].Icon;
            return (
              <button key={c.kind} type="button" onClick={() => pick(c.kind)}
                className="surface surface-interactive flex min-h-24 min-w-0 items-start gap-4 p-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 motion-reduce:transition-none motion-reduce:hover:transform-none">
                <span className="grid size-11 shrink-0 place-items-center rounded-full bg-secondary text-secondary-foreground"><Icon className="size-5" aria-hidden /></span>
                <span className="min-w-0">
                  <span className="block text-base font-semibold">{t(c.label)}</span>
                  <span className="mt-0.5 block text-sm text-muted-foreground">{t(c.hint)}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  const setDx = (i: number, v: DxDraft) => patch({ dx: d.dx.map((x, j) => (j === i ? v : x)) });
  const setTx = (i: number, v: TxDraft) => patch({ tx: d.tx.map((x, j) => (j === i ? v : x)) });
  const card_ = "surface space-y-4 p-4";
  return (
    <form onSubmit={save} className="space-y-5 pb-2" aria-label={t("records.newTitle")} noValidate>
      {restored && (
        <p role="status" className="surface flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
          <span>{t("records.draftRestored")}</span>
          <button type="button" onClick={startOver} className="font-medium text-primary underline-offset-4 hover:underline">{t("records.startOver")}</button>
        </p>
      )}
      <button type="button" onClick={() => patch({ type: null })} className="inline-flex min-h-11 items-center gap-1.5 rounded-full text-sm font-medium text-primary outline-none underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
        <ArrowLeft className="size-4" aria-hidden />{t("records.changeType")}{cardLabel && <span className="text-muted-foreground">· {t(cardLabel.label)}</span>}
      </button>

      <div className={card_}>
        {(d.type === "lab" || d.type === "imaging") && (
          <div role="group" aria-label={t("records.testsOrScan")} className="flex flex-wrap gap-2">
            <Chip on={d.type === "lab"} onClick={() => setD((c) => ({ ...c, type: "lab", title: c.titleTouched ? c.title : t(SUGGEST.lab) }))}>{t("records.kindLab")}</Chip>
            <Chip on={d.type === "imaging"} onClick={() => setD((c) => ({ ...c, type: "imaging", title: c.titleTouched ? c.title : t(SUGGEST.imaging) }))}>{t("records.kindImaging")}</Chip>
          </div>
        )}
        <Field label={t("records.fTitle")} hint={t("records.fTitleHint")}>
          {(id) => <Input id={id} ref={titleRef} className={inputClass} value={d.title} aria-invalid={titleBad || undefined} aria-required
            onChange={(e) => { setTitleBad(false); patch({ title: e.target.value, titleTouched: true }); }} />}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={isStay ? t("records.fStarted") : t("records.fDate")}>{(id) => <Input id={id} type="date" className={inputClass} value={d.date} onChange={(e) => patch({ date: e.target.value })} />}</Field>
          {isStay && !d.ongoing && <Field label={t("records.fEnded")}>{(id) => <Input id={id} type="date" className={inputClass} value={d.endDate} min={d.date || undefined} onChange={(e) => patch({ endDate: e.target.value })} />}</Field>}
        </div>
        {isStay && (
          <button type="button" role="switch" aria-checked={d.ongoing} onClick={() => patch({ ongoing: !d.ongoing, endDate: "" })}
            className="flex min-h-11 w-full items-center justify-between gap-3 rounded-2xl border bg-card/60 px-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
            <span className="text-sm font-medium">{t("records.stillIn")}</span>
            <span className={`flex h-7 w-12 shrink-0 items-center rounded-full border p-0.5 transition-colors motion-reduce:transition-none ${d.ongoing ? "border-primary bg-primary" : "bg-muted"}`} aria-hidden>
              <span className={`size-5 rounded-full bg-card shadow-sm transition-transform duration-200 ease-[var(--ease-spring)] motion-reduce:transition-none ${d.ongoing ? "translate-x-5" : ""}`} />
            </span>
          </button>
        )}
      </div>

      <div className={card_}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={isStay ? t("records.fHospital") : t("records.fClinic")}>
            {(id) => <><Input id={id} list={clinicList} className={inputClass} value={d.clinic} onChange={(e) => patch({ clinic: e.target.value })} autoComplete="off" />
              <datalist id={clinicList}>{clinics.map((c) => <option key={c} value={c} />)}</datalist></>}
          </Field>
          <Field label={t("records.fDepartment")}>{(id) => <Input id={id} className={inputClass} value={d.department} onChange={(e) => patch({ department: e.target.value })} />}</Field>
          <Field label={t("records.fDoctor")} className="sm:col-span-2">{(id) => <Input id={id} className={inputClass} value={d.doctor} onChange={(e) => patch({ doctor: e.target.value })} />}</Field>
        </div>
        <Field label={t("records.fReason")}>{(id) => <Textarea id={id} rows={3} value={d.reason} onChange={(e) => patch({ reason: e.target.value })} />}</Field>
      </div>

      <section className={card_} aria-labelledby="dx-h">
        <div><h2 id="dx-h" className="text-base font-semibold">{t("records.dxTitle")}</h2><p className="text-sm text-muted-foreground">{t("records.dxHint")}</p></div>
        {d.dx.map((x, i) => (
          <div key={x.key} className="space-y-3 rounded-2xl border bg-card/60 p-3">
            <DiagnosisFields value={x} onChange={(v) => setDx(i, v)} autoFocus={i === d.dx.length - 1 && !x.name} />
            <Button type="button" variant="ghost" size="lg" onClick={() => patch({ dx: d.dx.filter((_, j) => j !== i) })}><Trash2 aria-hidden />{t("records.remove")}</Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="lg" onClick={() => patch({ dx: [...d.dx, emptyDx(key())] })}><Plus aria-hidden />{t("records.addDiagnosis")}</Button>
      </section>

      <section className={card_} aria-labelledby="tx-h">
        <div><h2 id="tx-h" className="text-base font-semibold">{t("records.txTitle")}</h2><p className="text-sm text-muted-foreground">{t("records.txHint")}</p></div>
        {d.tx.map((x, i) => (
          <div key={x.key} className="space-y-3 rounded-2xl border bg-card/60 p-3">
            <TreatmentFields value={x} onChange={(v) => setTx(i, v)} autoFocus={i === d.tx.length - 1 && !x.name} />
            <Button type="button" variant="ghost" size="lg" onClick={() => patch({ tx: d.tx.filter((_, j) => j !== i) })}><Trash2 aria-hidden />{t("records.remove")}</Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="lg" onClick={() => patch({ tx: [...d.tx, emptyTx(key())] })}><Plus aria-hidden />{t("records.addTreatment")}</Button>
      </section>

      <section className={card_} aria-labelledby="q-h">
        <div><h2 id="q-h" className="text-base font-semibold">{t("records.qTitle")}</h2><p className="text-sm text-muted-foreground">{t("records.qHint")}</p></div>
        {d.questions.map((q, i) => (
          <div key={q.key} className="flex items-center gap-2">
            <Input aria-label={t("records.qLine", { n: i + 1 })} className={inputClass} value={q.text} autoFocus={i === d.questions.length - 1 && !q.text}
              onChange={(e) => patch({ questions: d.questions.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (q.text.trim()) patch({ questions: [...d.questions, { key: key(), text: "" }] }); } }} />
            <Button type="button" variant="ghost" size="icon-lg" className="size-11" aria-label={t("records.remove")} onClick={() => patch({ questions: d.questions.filter((_, j) => j !== i) })}><Trash2 aria-hidden /></Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="lg" onClick={() => patch({ questions: [...d.questions, { key: key(), text: "" }] })}><Plus aria-hidden />{t("records.addQuestion")}</Button>
      </section>

      <div className={card_}>
        <Field label={t("records.fNotes")}>{(id) => <Textarea id={id} rows={4} value={d.details} onChange={(e) => patch({ details: e.target.value })} />}</Field>
      </div>

      <div className="sticky bottom-0 z-20 -mx-4 space-y-2 border-t bg-background/92 px-4 py-3 backdrop-blur md:mx-0 md:rounded-3xl md:border">
        <ErrorLine message={error} />
        <div className="flex items-center gap-3">
          <Button type="submit" size="lg" className="h-12 flex-1 text-base md:flex-none md:px-10" disabled={saving}>{saving ? t("records.saving") : t("records.save")}</Button>
          <p className="hidden text-sm text-muted-foreground sm:block">{t("records.onlyTitleNeeded")}</p>
        </div>
      </div>
    </form>
  );
}
