"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { UserSettings } from "@/lib/types";
import { useStatus } from "./use-status";

const toNumber = (text: string): number | null => (text.trim() === "" ? null : Number(text));

export function ProfileForm({ initial }: { initial: UserSettings }) {
  const { t } = useI18n();
  const [latitude, setLatitude] = useState(initial.latitude?.toString() ?? "");
  const [longitude, setLongitude] = useState(initial.longitude?.toString() ?? "");
  const [bedtime, setBedtime] = useState(initial.bedtime);
  const [timezone, setTimezone] = useState(initial.timezone);
  const [saving, setSaving] = useState(false);
  const [status, show] = useStatus();

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); show(null);
    try {
      await sendJson<UserSettings>("settings", "PATCH", { latitude: toNumber(latitude), longitude: toNumber(longitude), bedtime, timezone: timezone.trim() });
      show({ text: t("settings.profileSaved"), ok: true });
    } catch (error) {
      show({ text: (error as Error).message, ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("settings.latitude")}</span>
          <Input inputMode="decimal" value={latitude} onChange={(e) => setLatitude(e.target.value)} placeholder="52.52" className="tnum" autoComplete="off" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("settings.longitude")}</span>
          <Input inputMode="decimal" value={longitude} onChange={(e) => setLongitude(e.target.value)} placeholder="13.41" className="tnum" autoComplete="off" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("settings.bedtime")}</span>
          <Input type="time" value={bedtime} onChange={(e) => setBedtime(e.target.value)} className="tnum" /></label>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("settings.timezone")}</span>
          <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder={initial.detected_timezone} autoComplete="off" spellCheck={false} /></label>
      </div>
      <p className="text-sm text-muted-foreground">{t("settings.profileHelp", { detected: initial.detected_timezone })}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={saving} className="h-auto min-h-9 whitespace-normal py-2">{saving ? t("settings.saving") : t("settings.profileSave")}</Button>
        {status && <p aria-live="polite" role={status.ok ? "status" : "alert"} className={`text-sm ${status.ok ? "text-muted-foreground" : "text-outrange"}`}>{status.text}</p>}
      </div>
    </form>
  );
}
