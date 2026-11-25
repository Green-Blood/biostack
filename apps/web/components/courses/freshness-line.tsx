"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { Freshness, FreshnessItem } from "@/lib/types";
import { ageText, intervalText } from "./age";

/** Age of the latest result with a status in words and icon, the re-test guide, and a control to change it for this marker. */
export function FreshnessLine({ markerKey }: { markerKey: string }) {
  const i18n = useI18n();
  const { t, tp } = i18n;
  const [item, setItem] = useState<FreshnessItem | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [unitMode, setUnitMode] = useState<"days" | "months">("months");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    let live = true;
    getJson<Freshness>("freshness").then((f) => { if (live) setItem(f.items.find((x) => x.marker_key === markerKey) ?? null); }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [markerKey]);

  if (failed) return <p className="text-sm text-muted-foreground">{t("courses.freshFailed")}</p>;
  if (!item) return null;

  const tone = item.status === "overdue" ? { Icon: AlertTriangle, cls: "text-outrange", word: t("courses.statusOverdue") }
    : item.status === "due" ? { Icon: Clock, cls: "text-warn", word: t("courses.statusDue") }
      : { Icon: CheckCircle2, cls: "text-ok", word: t("courses.statusFresh") };

  function startEditing() {
    const d = item?.retest_days;
    if (d && d >= 60 && d % 30 === 0) { setUnitMode("months"); setValue(String(d / 30)); } else { setUnitMode("days"); setValue(d ? String(d) : "90"); }
    setMessage(null); setOpen(true);
  }
  async function put(days: number | null) {
    setBusy(true); setMessage(null);
    try {
      const updated = await sendJson<FreshnessItem>(`freshness/${encodeURIComponent(markerKey)}/interval`, "PUT", { days });
      setItem(updated); setOpen(false); setMessage({ text: t("courses.intervalSaved"), ok: true });
    } catch (e) { setMessage({ text: (e as Error).message, ok: false }); } finally { setBusy(false); }
  }
  function save(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(value);
    if (!Number.isInteger(n) || n < 1) { setMessage({ text: t("courses.intervalInvalid"), ok: false }); return; }
    void put(unitMode === "months" ? n * 30 : n);
  }

  return (
    <div className="space-y-2 text-sm">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="tnum">{t("courses.measured", { age: ageText(i18n, item.age_days) })}</span>
        <span aria-hidden className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">{t("courses.intervalLine", { interval: intervalText(i18n, item.retest_days) })}{item.interval_source === "custom" && ` (${t("courses.intervalCustom")})`}</span>
        <span aria-hidden className="text-muted-foreground">—</span>
        <span className={`inline-flex items-center gap-1.5 font-medium ${tone.cls}`}><tone.Icon className="size-4" aria-hidden />{tone.word}</span>
        {item.status === "fresh" && item.due_in_days !== null && item.due_in_days > 0 && <span className="text-muted-foreground tnum">({tp("courses.dueIn", item.due_in_days)})</span>}
      </p>
      {!open && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>{t("courses.ruleOfThumb")}</span>
          <Button size="xs" variant="ghost" onClick={startEditing} aria-expanded={false}>{t("courses.intervalChange")}</Button>
        </p>
      )}
      {open && (
        <form onSubmit={save} className="surface flex flex-wrap items-end gap-3 p-3" aria-label={t("courses.intervalChange")}>
          <label className="space-y-1 text-xs font-medium">{t("courses.intervalLabel")}
            <Input type="number" min={1} inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} className="tnum w-24" /></label>
          <label className="space-y-1 text-xs font-medium"><span className="sr-only">{t("courses.intervalLabel")}</span>
            <select value={unitMode} onChange={(e) => setUnitMode(e.target.value as "days" | "months")} className="block h-9 rounded-2xl border bg-background px-2.5 text-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
              <option value="months">{t("courses.unitMonths")}</option><option value="days">{t("courses.unitDays")}</option>
            </select></label>
          <Button type="submit" disabled={busy}>{t("courses.intervalSave")}</Button>
          {item.interval_source === "custom" && <Button type="button" variant="outline" disabled={busy} onClick={() => put(null)}>{t("courses.intervalReset")}</Button>}
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>{t("courses.cancel")}</Button>
          <p className="basis-full text-xs text-muted-foreground">{t("courses.ruleOfThumb")}</p>
        </form>
      )}
      <p aria-live="polite" role={message?.ok === false ? "alert" : "status"} className={`text-xs ${message?.ok === false ? "text-outrange" : "text-muted-foreground"}`}>{message?.text}</p>
    </div>
  );
}
