"use client";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { todayIso } from "@/lib/format-date";
import { sendJson } from "@/lib/request";
import type { JournalCategory, JournalEntry } from "@/lib/types";

export const CATEGORIES: { value: JournalCategory; label: Key }[] = [
  { value: "symptom", label: "journal.catSymptom" }, { value: "doctor_visit", label: "journal.catDoctorVisit" }, { value: "note", label: "journal.catNote" },
];

export function EntryForm({ onSaved }: { onSaved: (entry: JournalEntry) => void }) {
  const [category, setCategory] = useState<JournalCategory>("symptom");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(todayIso);
  const [severity, setSeverity] = useState(5);
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const group = useId();
  const { t } = useI18n();
  const isSymptom = category === "symptom";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) { setMessage({ text: t("journal.needTitle"), ok: false }); return; }
    setSaving(true); setMessage(null);
    try {
      const saved = await sendJson<JournalEntry>("journal", "POST", {
        entry_date: date, category, title, description,
        severity_1_10: isSymptom ? severity : null, body_location: isSymptom && location.trim() ? location.trim() : null,
      });
      onSaved(saved); setTitle(""); setDescription(""); setLocation(""); setMessage({ text: t("journal.saved"), ok: true });
    } catch (error) {
      setMessage({ text: (error as Error).message, ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4" aria-label={t("journal.formLabel")}>
      <fieldset className="flex flex-wrap gap-2">
        <legend className="sr-only">{t("journal.entryType")}</legend>
        {CATEGORIES.map((c) => (
          <label key={c.value} className="cursor-pointer">
            <input type="radio" name={group} value={c.value} checked={category === c.value} onChange={() => setCategory(c.value)} className="peer sr-only" />
            <span className="inline-flex h-9 items-center rounded-2xl border px-3.5 text-sm transition-colors peer-checked:border-[var(--data)] peer-checked:bg-accent peer-checked:font-medium peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50">{t(c.label)}</span>
          </label>
        ))}
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-[1fr_11rem]">
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("journal.fieldTitle")}</span>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={isSymptom ? t("journal.phSymptom") : category === "doctor_visit" ? t("journal.phDoctor") : t("journal.phNote")} autoComplete="off" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("journal.fieldDate")}</span>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="tnum" /></label>
      </div>
      {isSymptom && (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1.5 text-sm"><span className="font-medium tnum">{t("journal.severity", { value: severity })}</span>
            <input type="range" min={1} max={10} value={severity} onChange={(e) => setSeverity(Number(e.target.value))} className="block h-8 w-full accent-[var(--data)]" /></label>
          <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("journal.bodyLocation")}</span>
            <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder={t("journal.bodyLocationPh")} autoComplete="off" /></label>
        </div>
      )}
      <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("journal.details")}</span>
        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} /></label>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={saving}>{saving ? t("journal.saving") : t("journal.save")}</Button>
        <p aria-live="polite" role={message?.ok === false ? "alert" : "status"} className={`text-sm ${message?.ok === false ? "text-outrange" : "text-muted-foreground"}`}>{message?.text}</p>
      </div>
    </form>
  );
}
