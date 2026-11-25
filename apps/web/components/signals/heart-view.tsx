"use client";
import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, HeartPulse, Waypoints } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { dayMs } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { Context, SignalSeries, SignalSeriesMap } from "@/lib/types";
import { LeadStats, leadOf } from "./lead-stats";
import { MetricChart } from "./metric-chart";
import { DAILY_PERIOD, firstDate, HEART_KEYS, metricText, toChartPoints, type MetricKey } from "./metric-model";
import { anchorOf, IMPORT_HREF } from "./format";
import { Segmented } from "./segmented";

type Hrv = "hrv_sdnn" | "hrv_rmssd";
type Props = { data: SignalSeriesMap; context: Context | null };

function HeartEmpty() {
  const { t } = useI18n();
  return (
    <section className="empty-state flex flex-col items-center gap-3 px-6 py-10 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary"><HeartPulse className="size-6" aria-hidden /></span>
      <h2 className="text-xl font-semibold">{t("heart.emptyTitle")}</h2>
      <p className="max-w-prose text-sm text-muted-foreground">{t("heart.emptyText")}</p>
      <Link href={IMPORT_HREF} className={buttonVariants({ size: "lg" })}>{t("signals.emptyAction")}<ArrowRight aria-hidden /></Link>
    </section>
  );
}

export function HeartView({ data, context }: Props) {
  const i18n = useI18n();
  const { t } = i18n;
  const s = useMemo(() => Object.fromEntries(Object.entries(data.series).filter(([, v]) => v.points.length)) as Partial<Record<MetricKey, SignalSeries>>, [data]);
  const today = data.today;
  const todayMs = dayMs(today); // the charts' "today" marker: the real today
  const anchorMs = dayMs(anchorOf(data)); // where the period windows end: the data's last day when it is old
  const [period, setPeriod] = useState<Period>(DAILY_PERIOD);
  const [hrv, setHrv] = useState<Hrv>("hrv_sdnn");

  const times = useMemo(() => HEART_KEYS.flatMap((k) => s[k]?.points.map((p) => dayMs(p.date)) ?? []), [s]);
  const domain = useMemo(() => periodDomain(period, times, anchorMs), [period, times, anchorMs]);
  const points = useMemo(() => {
    const lowest = new Map((s.spo2_min?.points ?? []).map((p) => [p.date, t("heart.spo2Lowest", { value: metricText(i18n.formatNumber, "spo2_min", p.value), unit: s.spo2_min!.unit })]));
    const out: Partial<Record<MetricKey, ReturnType<typeof toChartPoints>>> = {};
    for (const k of HEART_KEYS) if (s[k]) out[k] = toChartPoints(s[k]!, k, k === "spo2_avg" ? lowest : undefined);
    return out;
  }, [s, t, i18n.formatNumber]);

  if (!times.length) return <HeartEmpty />;
  const first = firstDate(HEART_KEYS.map((k) => s[k]));
  const chart = (key: MetricKey, extra: { note?: string; action?: ReactNode; title?: string; id?: string } = {}) => s[key] && (
    <MetricChart id={extra.id ?? `chart-${key}`} title={extra.title ?? s[key]!.name} unit={s[key]!.unit} points={points[key] ?? []}
      context={context} domain={domain} todayMs={todayMs} note={extra.note} action={extra.action} />
  );
  const lead = [
    leadOf(i18n, "resting_hr", s.resting_hr), leadOf(i18n, "hrv_sdnn", s.hrv_sdnn), leadOf(i18n, "skin_temp_delta", s.skin_temp_delta),
    leadOf(i18n, "spo2_avg", s.spo2_avg), leadOf(i18n, "respiratory_rate", s.respiratory_rate),
  ].filter((l) => l.text !== null);

  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <LeadStats items={lead} label={t("heart.leadLabel")} />
        <p className="text-xs text-muted-foreground">{t("heart.leadNote")}</p>
      </div>

      <Link href="/graph" className="surface surface-interactive flex items-center gap-4 p-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Waypoints className="size-5" aria-hidden /></span>
        <span className="min-w-0 flex-1">
          <span className="block font-medium">{t("heart.graphTitle")}</span>
          <span className="block text-sm text-muted-foreground">{t("heart.graphText")}</span>
        </span>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </Link>

      <section aria-labelledby="heart-charts-h" className="space-y-4">
        <h2 id="heart-charts-h" className="text-2xl font-semibold">{t("heart.chartsTitle")}</h2>
        <p className="max-w-prose text-sm text-muted-foreground">{t("heart.chartsText")}</p>
        <PeriodSelector value={period} onChange={setPeriod} minDate={first ?? undefined} maxDate={today} />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="xl:col-span-2">
            {chart(s[hrv] ? hrv : "hrv_sdnn", {
              id: "chart-hrv_sdnn", title: t("heart.hrvTitle"), note: t(hrv === "hrv_sdnn" ? "heart.sdnnNote" : "heart.rmssdNote"),
              action: s.hrv_rmssd && s.hrv_sdnn ? (
                <Segmented<Hrv> value={hrv} onChange={setHrv} label={t("heart.hrvMeasure")}
                  options={[{ value: "hrv_sdnn", label: "SDNN" }, { value: "hrv_rmssd", label: "RMSSD" }]} />
              ) : undefined,
            })}
          </div>
          {chart("resting_hr", { note: t("heart.restingNote") })}
          {chart("skin_temp_delta", { note: t("heart.skinNote") })}
          {chart("spo2_avg", { note: s.spo2_min ? t("heart.spo2Note") : undefined })}
          {chart("respiratory_rate", { note: t("heart.respNote") })}
        </div>
      </section>
    </div>
  );
}
