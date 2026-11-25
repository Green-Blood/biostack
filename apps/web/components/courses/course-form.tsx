"use client";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { Course, CourseInput, MarkerSummary, Preset } from "@/lib/types";

type Mode = "days" | "end" | "open";
type MarkerOption = { marker_key: string; display_name: string };

const modeOf = (c?: Course): Mode => (c?.days != null ? "days" : c?.end_date ? "end" : c ? "open" : "days");

/** Add or edit a course. Never suggests doses; every field is the owner's own free text. */
export function CourseForm({ course, initialMarker, onSaved, onCancel }: {
  course?: Course; initialMarker?: MarkerOption; onSaved: (c: Course) => void; onCancel: () => void;
}) {
  const { t } = useI18n();
  const lockedCore = course ? !course.editable : false;
  const [name, setName] = useState(course?.name ?? "");
  const [dosage, setDosage] = useState(course?.dosage ?? "");
  const [start, setStart] = useState(course?.start_date ?? todayIso());
  const [mode, setMode] = useState<Mode>(modeOf(course));
  const [days, setDays] = useState(course?.days != null ? String(course.days) : "30");
  const [end, setEnd] = useState(course?.end_date ?? "");
  const [marker, setMarker] = useState(course ? (course.target_marker_key ?? "") : (initialMarker?.marker_key ?? ""));
  const [notes, setNotes] = useState(course?.notes ?? "");
  const [options, setOptions] = useState<MarkerOption[]>(initialMarker ? [initialMarker] : []);
  const [names, setNames] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const group = useId();
  const listId = useId();

  useEffect(() => {
    let live = true;
    getJson<MarkerSummary[]>("biomarkers").then((all) => {
      if (!live) return;
      const seen = new Map<string, MarkerOption>();
      for (const m of [...(initialMarker ? [initialMarker] : []), ...all]) if (!seen.has(m.marker_key)) seen.set(m.marker_key, { marker_key: m.marker_key, display_name: m.display_name });
      setOptions([...seen.values()].sort((a, b) => a.display_name.localeCompare(b.display_name)));
    }).catch(() => { /* picker stays with what we have; the field is optional */ });
    getJson<Preset[]>("supplements/presets").then((p) => { if (live) setNames([...new Set(p.map((x) => x.item_name))]); }).catch(() => { /* suggestions are optional */ });
    return () => { live = false; };
  }, [initialMarker]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    let problem: string | null = null;
    if (!lockedCore) {
      if (!name.trim()) problem = t("courses.needName");
      else if (mode === "days" && !(Number(days) >= 1)) problem = t("courses.needDays");
      else if (mode === "end" && !end) problem = t("courses.needEnd");
      else if (mode === "end" && end < start) problem = t("courses.endBeforeStart");
    }
    if (problem) { setError(problem); return; }
    const body: CourseInput = lockedCore
      ? { target_marker_key: marker || null, notes }
      : {
        name: name.trim(), dosage: dosage.trim(), start_date: start, notes, target_marker_key: marker || null,
        days: mode === "days" ? Math.round(Number(days)) : null, end_date: mode === "end" ? end : null,
      };
    setSaving(true); setError(null);
    try {
      const saved = course ? await sendJson<Course>(`courses/${course.id}`, "PATCH", body) : await sendJson<Course>("courses", "POST", body);
      onSaved(saved);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const select = "h-9 w-full rounded-2xl border bg-background px-2.5 text-sm focus-visible:border-ring focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50";
  return (
    <form onSubmit={save} className="space-y-4" aria-label={course ? t("courses.editTitle") : t("courses.addTitle")}>
      {lockedCore && <p className="text-sm text-muted-foreground">{t("courses.readOnlyNote")}</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("courses.fieldWhat")}</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("courses.fieldWhatPh")} list={listId} autoComplete="off" disabled={lockedCore} />
          <datalist id={listId}>{names.map((n) => <option key={n} value={n} />)}</datalist></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("courses.fieldDose")}</span>
          <Input value={dosage} onChange={(e) => setDosage(e.target.value)} placeholder={t("courses.fieldDosePh")} autoComplete="off" disabled={lockedCore} /></label>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("courses.fieldStart")}</span>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="tnum" disabled={lockedCore} /></label>
        <fieldset className="space-y-1.5 text-sm" disabled={lockedCore}>
          <legend className="font-medium">{t("courses.fieldDuration")}</legend>
          <div className="flex flex-wrap gap-2">
            {([["days", "courses.durDays"], ["end", "courses.durEnd"], ["open", "courses.durOpen"]] as const).map(([value, label]) => (
              <label key={value} className="cursor-pointer">
                <input type="radio" name={group} value={value} checked={mode === value} onChange={() => setMode(value)} className="peer sr-only" />
                <span className="inline-flex h-9 items-center rounded-2xl border px-3 text-sm peer-checked:border-[var(--data)] peer-checked:bg-accent peer-checked:font-medium peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50 peer-disabled:opacity-50">{t(label)}</span>
              </label>
            ))}
          </div>
          {mode === "days" && <Input type="number" min={1} inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} aria-label={t("courses.fieldDays")} className="tnum w-28" />}
          {mode === "end" && <Input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} aria-label={t("courses.fieldEnd")} className="tnum" />}
        </fieldset>
      </div>
      <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("courses.fieldMarker")}</span>
        <select value={marker} onChange={(e) => setMarker(e.target.value)} className={select}>
          <option value="">{t("courses.markerNone")}</option>
          {options.map((m) => <option key={m.marker_key} value={m.marker_key}>{m.display_name}</option>)}
        </select></label>
      <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("courses.fieldNotes")}</span>
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} /></label>
      <p className="text-xs text-muted-foreground">{t("courses.sectionIntro")} {t("courses.caveat")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={saving}>{saving ? t("courses.saving") : t("courses.save")}</Button>
        <Button type="button" size="lg" variant="outline" onClick={onCancel}>{t("courses.cancel")}</Button>
        <p aria-live="polite" role="alert" className="text-sm text-outrange">{error}</p>
      </div>
    </form>
  );
}
