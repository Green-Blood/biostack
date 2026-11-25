"use client";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { Preset } from "@/lib/types";
import { useStatus } from "./use-status";

const BLANK: Preset = { item_name: "", dosage: null, unit: "mg", category: "supplement", half_life_hours: null };
const toNumber = (text: string): number | null => (text.trim() === "" ? null : Number(text));

export function PresetsEditor({ initial }: { initial: Preset[] }) {
  const { t } = useI18n();
  const [rows, setRows] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [status, show] = useStatus();
  const change = (index: number, patch: Partial<Preset>) => { setRows((all) => all.map((r, i) => (i === index ? { ...r, ...patch } : r))); show(null); };

  async function save() {
    const named = rows.filter((r) => r.item_name.trim());
    setSaving(true); show(null);
    try {
      setRows(await sendJson<Preset[]>("supplements/presets", "PUT", named));
      show({ text: t("settings.presetSaved"), ok: true });
    } catch (error) {
      show({ text: (error as Error).message, ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {rows.length === 0 && <p className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">{t("settings.presetsEmpty")}</p>}
      <ul className="space-y-4">
        {rows.map((row, i) => (
          <li key={i} className="grid grid-cols-2 items-end gap-3 rounded-2xl border p-3 sm:grid-cols-[minmax(0,1.6fr)_5rem_5rem_9rem_7rem_auto]">
            <label className="col-span-2 space-y-1 text-sm sm:col-span-1"><span className="font-medium">{t("settings.presetName")}</span>
              <Input value={row.item_name} onChange={(e) => change(i, { item_name: e.target.value })} autoComplete="off" /></label>
            <label className="space-y-1 text-sm"><span className="font-medium">{t("settings.presetDose")}</span>
              <Input inputMode="decimal" value={row.dosage ?? ""} onChange={(e) => change(i, { dosage: toNumber(e.target.value) })} className="tnum" /></label>
            <label className="space-y-1 text-sm"><span className="font-medium">{t("settings.presetUnit")}</span>
              <Input value={row.unit} onChange={(e) => change(i, { unit: e.target.value })} autoComplete="off" /></label>
            <label className="space-y-1 text-sm"><span className="font-medium">{t("settings.presetKind")}</span>
              <select value={row.category} onChange={(e) => change(i, { category: e.target.value as Preset["category"] })}
                className="h-8 w-full rounded-2xl border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30">
                <option value="stimulant">{t("settings.kindStimulant")}</option><option value="supplement">{t("settings.kindSupplement")}</option><option value="medication">{t("settings.kindMedication")}</option>
              </select></label>
            <label className="space-y-1 text-sm"><span className="font-medium">{t("settings.presetHalfLife")}</span>
              <Input inputMode="decimal" value={row.half_life_hours ?? ""} onChange={(e) => change(i, { half_life_hours: toNumber(e.target.value) })} className="tnum" placeholder={t("settings.optional")} /></label>
            <Button variant="ghost" size="icon" onClick={() => setRows((all) => all.filter((_, j) => j !== i))} aria-label={t("settings.presetRemove", { name: row.item_name || t("settings.presetThis") })}><Trash2 aria-hidden /></Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="lg" onClick={() => setRows((all) => [...all, BLANK])}><Plus aria-hidden /> {t("settings.presetAdd")}</Button>
        <Button size="lg" onClick={save} disabled={saving}>{saving ? t("settings.presetSaving") : t("settings.presetSave")}</Button>
        {status && <p aria-live="polite" role={status.ok ? "status" : "alert"} className={`text-sm ${status.ok ? "text-muted-foreground" : "text-outrange"}`}>{status.text}</p>}
      </div>
    </div>
  );
}
