"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { EnvironmentReading } from "@/lib/types";

export function EnvironmentCard({ initial }: { initial: EnvironmentReading | null }) {
  const { t, locale, formatNumber } = useI18n();
  const show = (value: number | null, digits = 0) => (value === null ? t("settings.envNoData") : formatNumber(value, { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  const clockTime = (iso: string) => new Date(iso).toLocaleTimeString(locale === "ru" ? "ru-RU" : "en-GB", { hour: "2-digit", minute: "2-digit" });
  const [reading, setReading] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setBusy(true); setError(null);
    try { setReading(await sendJson<EnvironmentReading>("environment/refresh", "POST")); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm text-muted-foreground">{t("settings.envIntro")}</p>
      {reading ? (
        <dl className="tnum grid max-w-lg grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          <div><dt className="text-muted-foreground">PM2.5</dt><dd>{show(reading.pm2_5, 1)} {t("settings.ugm3")}</dd></div>
          <div><dt className="text-muted-foreground">{t("settings.envAqi")}</dt><dd>{show(reading.aqi)}</dd></div>
          <div><dt className="text-muted-foreground">{t("settings.envPressure")}</dt><dd>{show(reading.pressure_mmHg)} {t("settings.mmHg")}</dd></div>
          <div><dt className="text-muted-foreground">{t("settings.envChange")}</dt><dd>{show(reading.pressure_delta_24h, 1)} {t("settings.mmHg")}</dd></div>
          <div><dt className="text-muted-foreground">{t("settings.envHumidity")}</dt><dd>{show(reading.humidity)}%</dd></div>
          <div><dt className="text-muted-foreground">{t("settings.envReadAt")}</dt><dd>{clockTime(reading.timestamp)}</dd></div>
        </dl>
      ) : <p className="text-sm">{t("settings.envEmpty")}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="lg" onClick={refresh} disabled={busy}>{busy ? t("settings.envRefreshing") : t("settings.envRefresh")}</Button>
        <p aria-live="polite" role="alert" className="text-sm text-outrange">{error}</p>
      </div>
    </div>
  );
}
