"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Footprints } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { inDomain, periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { dayMs } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { Context, SignalSeries, SignalSeriesMap, WorkoutList } from "@/lib/types";
import { clipDays, typeCounts, weeklyMeans, workoutsByDay } from "./activity-model";
import { anchorOf, duration, IMPORT_HREF } from "./format";
import { LeadStats, leadOf, type LeadStat } from "./lead-stats";
import { MetricChart } from "./metric-chart";
import { DAILY_PERIOD, ACTIVITY_KEYS, metricText, recentMean, toChartPoints, type MetricKey } from "./metric-model";
import { StepsChart } from "./steps-chart";
import { WorkoutStrip } from "./workout-strip";
import { WorkoutsList } from "./workouts-list";

type Props = { data: SignalSeriesMap; workouts: WorkoutList; context: Context | null };

function ActivityEmpty() {
  const { t } = useI18n();
  return (
    <section className="empty-state flex flex-col items-center gap-3 px-6 py-10 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary"><Footprints className="size-6" aria-hidden /></span>
      <h2 className="text-xl font-semibold">{t("activity.emptyTitle")}</h2>
      <p className="max-w-prose text-sm text-muted-foreground">{t("activity.emptyText")}</p>
      <Link href={IMPORT_HREF} className={buttonVariants({ size: "lg" })}>{t("signals.emptyAction")}<ArrowRight aria-hidden /></Link>
    </section>
  );
}

export function ActivityView({ data, workouts, context }: Props) {
  const i18n = useI18n();
  const { t, tp, formatDate } = i18n;
  const s = useMemo(() => Object.fromEntries(Object.entries(data.series).filter(([, v]) => v.points.length)) as Partial<Record<MetricKey, SignalSeries>>, [data]);
  const today = data.today;
  const todayMs = dayMs(today); // the charts' "today" marker: the real today
  const anchor = anchorOf(data); // where the period windows and "30 days" stats end: the data's last day when it is old
  const anchorMs = dayMs(anchor);
  const [period, setPeriod] = useState<Period>(DAILY_PERIOD);
  const [type, setType] = useState<number | null>(null);

  const dates = useMemo(() => [...ACTIVITY_KEYS.flatMap((k) => s[k]?.points.map((p) => p.date) ?? []), ...workouts.items.map((w) => w.local_date)].sort(), [s, workouts]);
  const times = useMemo(() => dates.map(dayMs), [dates]);
  const domain = useMemo(() => periodDomain(period, times, dayMs(anchorOf(data))), [period, times, data]);
  const weeks = useMemo(() => weeklyMeans(s.steps?.points ?? []), [s]);
  const inPeriod = useMemo(() => workouts.items.filter((w) => inDomain(dayMs(w.local_date), domain)), [workouts, domain]);
  const types = useMemo(() => typeCounts(inPeriod), [inPeriod]);
  const chosen = type !== null && types.some((ty) => ty.type_code === type) ? type : null;
  const listed = useMemo(() => (chosen === null ? inPeriod : inPeriod.filter((w) => w.type_code === chosen)), [inPeriod, chosen]);
  const byDay = useMemo(() => workoutsByDay(listed), [listed]);

  if (!dates.length) return <ActivityEmpty />;
  const [from, to] = clipDays(domain, dates[0], today);

  const steps30 = recentMean(s.steps?.points ?? [], anchor, 30);
  const recent = workouts.items.filter((w) => dayMs(w.local_date) > anchorMs - 30 * 86_400_000 && w.local_date <= anchor);
  const toDate = data.stale ? formatDate(anchor, { day: "numeric", month: "short", year: "numeric" }) : null;
  const lead: LeadStat[] = [
    leadOf(i18n, "steps", s.steps),
    { key: "steps30", name: toDate ? t("activity.steps30To", { date: toDate }) : t("activity.steps30"), unit: s.steps?.unit ?? "", text: steps30 ? metricText(i18n.formatNumber, "steps", steps30.mean) : null,
      date: null, position: null, range: null, sub: steps30 ? tp("activity.avgOfDays", steps30.n) : undefined, href: "#steps" },
    leadOf(i18n, "distance_m", s.distance_m, undefined, t("activity.kmUnit")),
    leadOf(i18n, "active_kcal", s.active_kcal),
    { key: "workouts30", name: toDate ? t("activity.workouts30To", { date: toDate }) : t("activity.workouts30"), unit: "", text: i18n.formatNumber(recent.length), date: null, position: null, range: null,
      sub: duration(i18n, recent.reduce((a, w) => a + w.duration_min, 0)).long, href: "#workouts" },
  ].filter((l) => l.text !== null);
  const metric = (key: "distance_m" | "active_kcal") => s[key] && (
    <MetricChart id={`chart-${key}`} title={s[key]!.name} unit={key === "distance_m" ? t("activity.kmUnit") : s[key]!.unit}
      points={toChartPoints(s[key]!, key)} context={context} domain={domain} todayMs={todayMs} />
  );

  return (
    <div className="space-y-10">
      <LeadStats items={lead} label={t("activity.leadLabel")} />
      <div className="space-y-2">
        <PeriodSelector value={period} onChange={setPeriod} minDate={dates[0]} maxDate={today} />
        <p className="max-w-prose text-sm text-muted-foreground">{t("activity.periodNote")}</p>
      </div>

      <section id="steps" aria-labelledby="steps-h" className="scroll-mt-24 space-y-3">
        <h2 id="steps-h" className="text-2xl font-semibold">{t("activity.stepsTitle")}</h2>
        <StepsChart points={s.steps?.points ?? []} weeks={weeks} domain={domain} context={context} />
      </section>

      {(s.distance_m || s.active_kcal) && (
        <section aria-labelledby="dist-h" className="space-y-3">
          <h2 id="dist-h" className="text-2xl font-semibold">{t("activity.distTitle")}</h2>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">{metric("distance_m")}{metric("active_kcal")}</div>
        </section>
      )}

      <section id="workouts" aria-labelledby="wo-h" className="scroll-mt-24 space-y-3">
        <h2 id="wo-h" className="text-2xl font-semibold">{t("activity.workoutsTitle")}</h2>
        <WorkoutStrip from={from} to={to} byDay={byDay} />
        <WorkoutsList items={listed} total={inPeriod.length} types={types} type={chosen} onType={setType} />
      </section>
    </div>
  );
}
