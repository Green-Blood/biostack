"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { Measurement, MeasurementKind, Profile } from "@/lib/types";
import { parseDecimal } from "./category";

const sane = (v: number | null, lo: number, hi: number) => v !== null && Number.isFinite(v) && v >= lo && v <= hi;

export function BodyCard({ profile, onChanged }: { profile: Profile; onChanged: () => void }) {
  const { t, formatDate, formatNumber } = useI18n();
  const [date, setDate] = useState(todayIso);
  const [kg, setKg] = useState("");
  const [cm, setCm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const n = (v: number) => formatNumber(v, { maximumFractionDigits: 1 });

  async function add(e: React.FormEvent) {
    e.preventDefault(); setOk(false);
    const w = parseDecimal(kg), c = parseDecimal(cm);
    if (!date || date > todayIso()) { setError(t("profile.errDate")); return; }
    if (w === null && c === null) { setError(t("profile.errNothing")); return; }
    if (w !== null && !sane(w, 20, 400)) { setError(t("profile.errWeight")); return; }
    if (c !== null && !sane(c, 30, 250)) { setError(t("profile.errWaist")); return; }
    setBusy(true); setError(null);
    try {
      const post = (kind: MeasurementKind, value: number) => sendJson<Measurement>("profile/measurements", "POST", { date, kind, value });
      if (w !== null) await post("weight", w);
      if (c !== null) await post("waist", c);
      setKg(""); setCm(""); setOk(true);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const touch = () => setOk(false);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        {profile.latest_weight ? (
          <div>
            <p className="eyebrow">{t("profile.latestWeight")}</p>
            <p className="font-heading text-4xl font-semibold tnum">{n(profile.latest_weight.kg)} <span className="text-lg font-normal text-muted-foreground">{t("profile.unitKg")}</span></p>
            <p className="text-sm text-muted-foreground tnum">{t("profile.latestWeightOn", { date: formatDate(profile.latest_weight.date) })}</p>
          </div>
        ) : <p className="text-muted-foreground">{t("profile.noWeight")}</p>}
        {profile.latest_waist && (
          <div>
            <p className="eyebrow">{t("profile.latestWaist")}</p>
            <p className="text-xl font-semibold tnum">{n(profile.latest_waist.cm)} <span className="text-sm font-normal text-muted-foreground">{t("profile.unitCm")}</span></p>
            <p className="text-sm text-muted-foreground tnum">{t("profile.latestWeightOn", { date: formatDate(profile.latest_waist.date) })}{profile.whtr != null && ` · ${t("profile.whtr", { v: formatNumber(profile.whtr, { maximumFractionDigits: 2, minimumFractionDigits: 2 }) })}`}</p>
          </div>
        )}
      </div>
      <form onSubmit={add} className="space-y-3 border-t pt-4" aria-label={t("profile.addWeightTitle")}>
        <h3 className="text-lg font-semibold">{t("profile.addWeightTitle")}</h3>
        <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(11rem,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <label className="block min-w-0 space-y-1.5 text-sm"><span className="font-medium">{t("profile.date")}</span>
            <Input type="date" value={date} max={todayIso()} onChange={(e) => { setDate(e.target.value); touch(); }} className="tnum" /></label>
          <label className="block min-w-0 space-y-1.5 text-sm"><span className="font-medium">{t("profile.weightKg")}</span>
            <Input inputMode="decimal" value={kg} onChange={(e) => { setKg(e.target.value); touch(); }} placeholder={t("profile.weightPh")} autoComplete="off" className="tnum" /></label>
          <label className="block min-w-0 space-y-1.5 text-sm"><span className="font-medium">{t("profile.waistCm")}</span>
            <Input inputMode="decimal" value={cm} onChange={(e) => { setCm(e.target.value); touch(); }} placeholder={t("profile.waistPh")} autoComplete="off" className="tnum" /></label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" disabled={busy}>{busy ? t("profile.adding") : t("profile.add")}</Button>
          <p aria-live="polite" role={error ? "alert" : "status"} className={`text-sm ${error ? "text-outrange" : "text-ok"}`}>{error ?? (ok ? t("profile.added") : "")}</p>
        </div>
      </form>
    </div>
  );
}
