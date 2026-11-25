"use client";
import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { cn } from "cn";
import { DEFAULT_PERIOD, periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { dayMs } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { OrganDetail } from "@/lib/types";
import { conclusionId, Conclusions } from "./conclusions";
import { ScanTable } from "./scan-table";
import { SeriesCharts } from "./series-charts";
import { buildContext } from "./table-model";

/** Opens the newest few conclusions by default; the rest stay one line each so ~100 scans remain scannable. */
const OPEN_BY_DEFAULT = 3;

function LaneToggle({ relatedOnly, onChange }: { relatedOnly: boolean; onChange: (v: boolean) => void }) {
  const { t } = useI18n();
  const opt = (value: boolean, label: string) => (
    <button type="button" role="radio" aria-checked={relatedOnly === value} onClick={() => onChange(value)}
      className={cn("h-7 rounded-xl px-3 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
        relatedOnly === value ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>{label}</button>
  );
  return (
    <div role="radiogroup" aria-label={t("organs.lanesLabel")} className="inline-flex rounded-2xl bg-muted p-[3px] text-sm">
      {opt(false, t("organs.lanesAll"))}{opt(true, t("organs.lanesRelated"))}
    </div>
  );
}

export function OrganView({ organ, today }: { organ: OrganDetail; today: string }) {
  const { t } = useI18n();
  const todayMs = dayMs(today);
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [relatedOnly, setRelatedOnly] = useState(false);
  const [open, setOpen] = useState<Set<number>>(() => new Set(organ.scans.slice(-OPEN_BY_DEFAULT).map((s) => s.record_id)));
  const context = useMemo(() => buildContext(organ, relatedOnly), [organ, relatedOnly]);
  const times = useMemo(() => organ.series.flatMap((s) => s.points.map((p) => dayMs(p.date))), [organ.series]);
  const domain = useMemo(() => periodDomain(period, times, todayMs), [period, times, todayMs]);
  const firstDate = organ.scans.find((s) => s.date)?.date ?? undefined;

  const openScan = useCallback((id: number) => {
    setOpen((prev) => new Set(prev).add(id));
    requestAnimationFrame(() => document.getElementById(conclusionId(id))?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, []);

  if (organ.scans.length === 0) {
    return (
      <div className="empty-state space-y-3 p-8 text-center">
        <p className="text-muted-foreground">{t("organs.emptyScans")}</p>
        <Link href="/records/new" className="text-primary underline-offset-4 hover:underline">{t("organs.addReport")}</Link>
      </div>
    );
  }
  const hasNumbers = organ.params.length > 0;
  const noneRelated = relatedOnly && organ.treatments.length > 0 && !organ.treatments.some((tr) => tr.related);

  return (
    <div className="space-y-10">
      {!hasNumbers && <p className="empty-state p-4 text-sm text-muted-foreground">{t("organs.noNumbersHint")}</p>}

      {organ.series.length > 0 && (
        <section aria-labelledby="charts-h" className="space-y-4">
          <h2 id="charts-h" className="text-2xl">{t("organs.chartsTitle")}</h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <PeriodSelector value={period} onChange={setPeriod} minDate={firstDate} maxDate={today} />
            {organ.treatments.length > 0 && <LaneToggle relatedOnly={relatedOnly} onChange={setRelatedOnly} />}
          </div>
          {noneRelated && <p className="text-sm text-muted-foreground">{t("organs.lanesNoneRelated")}</p>}
          <SeriesCharts organ={organ} context={context} domain={domain} todayMs={todayMs} />
        </section>
      )}

      {hasNumbers && (
        <section aria-labelledby="table-h" className="min-w-0 space-y-3">
          <h2 id="table-h" className="text-2xl">{t("organs.tableTitle")}</h2>
          <ScanTable organ={organ} onOpenScan={openScan} />
          <p className="max-w-prose text-sm text-muted-foreground">{t("organs.measurementsVary")}</p>
        </section>
      )}

      <section aria-labelledby="conclusions-h" className="space-y-3">
        <h2 id="conclusions-h" className="text-2xl">{t("organs.conclusionsTitle")}</h2>
        <Conclusions scans={organ.scans} aliases={organ.aliases} open={open} setOpen={setOpen} />
      </section>
    </div>
  );
}
