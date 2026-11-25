"use client";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { Profile, ProfileInput, ProfileSex } from "@/lib/types";
import { parseDecimal } from "./category";

type SexChoice = ProfileSex | "none";

export function BasicsForm({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const { t, tp, formatNumber } = useI18n();
  const [birth, setBirth] = useState(profile.birth_date ?? "");
  const [sex, setSex] = useState<SexChoice>(profile.sex ?? "none");
  const [height, setHeight] = useState(profile.height_cm != null ? formatNumber(profile.height_cm, { useGrouping: false }) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const group = useId();

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaved(false);
    const h = parseDecimal(height);
    if (birth && (birth > todayIso() || birth < "1900-01-01")) { setError(t("profile.errBirth")); return; }
    if (h !== null && !(Number.isFinite(h) && h >= 50 && h <= 260)) { setError(t("profile.errHeight")); return; }
    const body: ProfileInput = { birth_date: birth || null, sex: sex === "none" ? null : sex, height_cm: h };
    setSaving(true); setError(null);
    try {
      onSaved(await sendJson<Profile>("profile", "PUT", body));
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const touch = () => setSaved(false);
  return (
    <form onSubmit={save} className="space-y-4" aria-label={t("profile.basicsTitle")}>
      <div className="grid min-w-0 gap-4 sm:grid-cols-2">
        <label className="block min-w-0 space-y-1.5 text-sm"><span className="font-medium">{t("profile.birthDate")}</span>
          <Input type="date" value={birth} max={todayIso()} onChange={(e) => { setBirth(e.target.value); touch(); }} className="tnum" /></label>
        <label className="block min-w-0 space-y-1.5 text-sm"><span className="font-medium">{t("profile.height")}</span>
          <Input inputMode="decimal" value={height} onChange={(e) => { setHeight(e.target.value); touch(); }} placeholder={t("profile.heightPh")} autoComplete="off" className="tnum" /></label>
      </div>
      <fieldset className="space-y-1.5 text-sm">
        <legend className="font-medium">{t("profile.sex")}</legend>
        <div className="flex flex-wrap gap-2">
          {([["female", "profile.sexFemale"], ["male", "profile.sexMale"], ["none", "profile.sexNone"]] as const).map(([value, label]) => (
            <label key={value} className="cursor-pointer">
              <input type="radio" name={group} value={value} checked={sex === value} onChange={() => { setSex(value); touch(); }} className="peer sr-only" />
              <span className="inline-flex h-9 items-center rounded-2xl border px-3 text-sm peer-checked:border-[var(--data)] peer-checked:bg-accent peer-checked:font-medium peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50">{t(label)}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button type="submit" size="lg" disabled={saving}>{saving ? t("profile.saving") : t("profile.save")}</Button>
        <p className="text-sm text-muted-foreground tnum">{profile.age_years != null ? tp("profile.age", profile.age_years) : t("profile.ageNone")}</p>
        <p aria-live="polite" role={error ? "alert" : "status"} className={`text-sm ${error ? "text-outrange" : "text-ok"}`}>{error ?? (saved ? t("profile.saved") : "")}</p>
      </div>
    </form>
  );
}
