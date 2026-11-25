"use client";
import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Moon } from "lucide-react";
import { cn } from "cn";
import { buttonVariants } from "@/components/ui/button";
import { DEFAULT_PERIOD, inDomain, periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { dayMs } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { Context, SleepDetail, SleepList } from "@/lib/types";
import { BedtimeChart } from "./bedtime-chart";
import { Hypnogram } from "./hypnogram";
import { IMPORT_HREF } from "./overview";
import { autoGrouping, groupNights, type Grouping } from "./sleep-model";
import { SleepSummary } from "./sleep-summary";
import { StageBars } from "./stage-bars";

const GROUPS = [
  { g: "night", key: "signals.groupNight" },
  { g: "week", key: "signals.groupWeek" },
  { g: "month", key: "signals.groupMonth" },
] as const;

function GroupingSelector({ value, onChange }: { value: Grouping; onChange: (g: Grouping) => void }) {
  const { t } = useI18n();
  return (
    <div role="radiogroup" aria-label={t("signals.groupLabel")} className="inline-flex rounded-2xl bg-muted p-[3px] text-sm">
      {GROUPS.map(({ g, key }) => (
        <button key={g} type="button" role="radio" aria-checked={value === g} onClick={() => onChange(g)}
          className={cn("h-7 rounded-xl px-3 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
            value === g ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>
          {t(key)}
        </button>
      ))}
    </div>
  );
}

function SleepEmpty() {
  const { t } = useI18n();
  return (
    <section className="empty-state flex flex-col items-center gap-3 px-6 py-10 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary"><Moon className="size-6" aria-hidden /></span>
      <h2 className="text-xl font-semibold">{t("signals.sleepEmptyTitle")}</h2>
      <p className="max-w-prose text-sm text-muted-foreground">{t("signals.sleepEmptyText")}</p>
      <Link href={IMPORT_HREF} className={buttonVariants({ size: "lg" })}>{t("signals.emptyAction")}<ArrowRight aria-hidden /></Link>
    </section>
  );
}

type Props = { data: SleepList; context: Context | null; initialDetail: SleepDetail | null; today: string };

export function SleepView({ data, context, initialDetail, today }: Props) {
  const { t } = useI18n();
  const nights = data.nights; // newest first
  const todayMs = dayMs(today);
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [chosenGrouping, setChosenGrouping] = useState<Grouping | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(nights[0]?.session_id ?? null);

  const times = useMemo(() => nights.map((n) => dayMs(n.wake_date)), [nights]);
  const domain = useMemo(() => periodDomain(period, times, todayMs), [period, times, todayMs]);
  const shown = useMemo(() => nights.filter((_, i) => inDomain(times[i], domain)), [nights, times, domain]);
  const grouping = chosenGrouping ?? autoGrouping(shown.length);
  const slots = useMemo(() => groupNights(shown, grouping), [shown, grouping]);

  const select = useCallback((id: number, reveal: boolean) => {
    setSelectedId(id);
    if (reveal) requestAnimationFrame(() => document.getElementById("night-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }, []);

  if (!nights.length) return <SleepEmpty />;
  const firstDate = nights.at(-1)!.wake_date;

  return (
    <div className="space-y-10">
      <SleepSummary summary={data.summary} nights={nights} freshness={data} />

      <section aria-labelledby="bars-h" className="space-y-4">
        <h2 id="bars-h" className="text-2xl font-semibold">{t("signals.barsTitle")}</h2>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <PeriodSelector value={period} onChange={setPeriod} minDate={firstDate} maxDate={today} />
          <GroupingSelector value={grouping} onChange={setChosenGrouping} />
        </div>
        <StageBars slots={slots} grouping={grouping} domain={domain} context={context} selectedId={selectedId} onSelect={select} />
      </section>

      <section aria-labelledby="bed-h" className="space-y-3">
        <h2 id="bed-h" className="text-2xl font-semibold">{t("signals.bedTitle")}</h2>
        <p className="max-w-prose text-sm text-muted-foreground">{t("signals.bedText")}</p>
        <BedtimeChart nights={shown} domain={domain} todayMs={todayMs} selectedId={selectedId} />
      </section>

      <Hypnogram nights={nights} selectedId={selectedId} initial={initialDetail} onSelect={(id) => select(id, false)} />
    </div>
  );
}
