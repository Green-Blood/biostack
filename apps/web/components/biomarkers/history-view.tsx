"use client";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DemoBadge } from "@/components/demo-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { buildCaption } from "@/components/charts/caption";
import { signOf } from "@/components/charts/change";
import { DEFAULT_PERIOD, periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { RangeOverlay } from "@/components/charts/range-overlay";
import { TimeChart, type ChartPoint } from "@/components/charts/time-chart";
import { dayMs } from "@/components/charts/time-scale";
import { tierOf } from "@/components/charts/tiers";
import { FreshnessLine } from "@/components/courses/freshness-line";
import { MarkerCourses } from "@/components/courses/marker-courses";
import { MarkerExplanation } from "./marker-explanation";
import { StartCourse } from "@/components/courses/start-course";
import type { Context, MarkerHistory, MarkerHistoryExtras } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";

type History = MarkerHistory & MarkerHistoryExtras;
type Other = { marker_key: string; display_name: string };

function DeltaTable({ h }: { h: MarkerHistory }) {
  const { t, formatDate, formatNumber, unit } = useI18n();
  const num = (n: number, digits = 4) => formatNumber(n, { maximumFractionDigits: digits });
  if (!h.deltas.length) return null;
  return (
    <section aria-labelledby="deltas-h">
      <h2 id="deltas-h" className="mb-3 text-2xl">{t("charts.deltasTitle")}</h2>
      <div className="surface overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b text-left text-muted-foreground"><th className="px-4 py-2.5 font-medium">{t("charts.colPeriod")}</th><th className="px-4 py-2.5 text-right font-medium">{t("charts.colChange")}</th><th className="px-4 py-2.5 text-right font-medium">{t("charts.colPercent")}</th><th className="px-4 py-2.5 font-medium">{t("charts.colDirection")}</th></tr></thead>
          <tbody>
            {h.deltas.map((d) => (
              <tr key={d.from_date + d.to_date} className="border-b last:border-0">
                <td className="px-4 py-2.5 tnum">{t("charts.periodRange", { from: formatDate(d.from_date), to: formatDate(d.to_date) })}</td>
                <td className="px-4 py-2.5 text-right tnum">{signOf(d.abs)}{num(Math.abs(d.abs), 2)} {unit(h.unit)}</td>
                <td className="px-4 py-2.5 text-right tnum">{d.pct === null ? "—" : `${signOf(d.pct)}${num(Math.abs(d.pct), 1)}%`}</td>
                <td className="px-4 py-2.5">{d.stayed_in_range ? <Badge variant="secondary">{t("charts.stayed")}</Badge> : d.toward_range === null ? <span className="text-muted-foreground">{t("charts.noRangeToJudge")}</span> : d.toward_range ? <Badge variant="secondary">▲ {t("charts.toward")}</Badge> : <Badge variant="destructive">▼ {t("charts.away")}</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ComparePanel({ h }: { h: MarkerHistory }) {
  const { t, formatDate, formatNumber, unit } = useI18n();
  const num = (n: number, digits = 4) => formatNumber(n, { maximumFractionDigits: digits });
  const dates = h.points.map((p) => p.date);
  const [a, setA] = useState(dates[0]);
  const [b, setB] = useState(dates.at(-1)!);
  if (dates.length < 2) return null;
  const pa = h.points.find((p) => p.date === a)!, pb = h.points.find((p) => p.date === b)!;
  const diff = pb.value - pa.value;
  const sel = (v: string, set: (s: string) => void, label: string) => (
    <select aria-label={label} value={v} onChange={(e) => set(e.target.value)} className="h-8 rounded-xl border bg-card px-2 text-sm tnum">
      {dates.map((d) => <option key={d} value={d}>{formatDate(d)}</option>)}
    </select>
  );
  return (
    <section aria-labelledby="cmp-h">
      <h2 id="cmp-h" className="mb-3 text-2xl">{t("charts.compareTitle")}</h2>
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-4 text-sm shadow-card">
        {sel(a, setA, t("charts.firstDate"))} <span className="text-muted-foreground">{t("charts.versus")}</span> {sel(b, setB, t("charts.secondDate"))}
        <span className="tnum ml-auto text-base">{num(pa.value)} → {num(pb.value)} {unit(h.unit)} <span className="font-semibold">({signOf(diff)}{num(Math.abs(diff), 2)}{pa.value !== 0 ? `, ${signOf(diff)}${num(Math.abs((diff / Math.abs(pa.value)) * 100), 1)}%` : ""})</span></span>
      </div>
    </section>
  );
}

function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function HistoryView({ h, context, others, today }: { h: History; context: Context; others: Other[]; today?: string }) {
  const i18n = useI18n();
  const { t, tp, formatDate, formatNumber, unit } = i18n;
  const num = (n: number) => formatNumber(n, { maximumFractionDigits: 4 });
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [todayIso] = useState(() => today ?? localToday());
  const todayMs = dayMs(todayIso);
  const tiers = useMemo(() => h.tiers ?? [], [h.tiers]);
  const points = h.points as ChartPoint[];
  const domain = useMemo(() => periodDomain(period, points.map((p) => dayMs(p.date)), todayMs), [period, points, todayMs]);

  const last = points.at(-1);
  if (!last) {
    return (
      <div className="space-y-4">
        <MarkerExplanation markerKey={h.marker_key} />
        <p className="rounded-xl border border-dashed p-6 text-muted-foreground">{t("charts.textOnly")}</p>
        <ul className="space-y-1 text-sm">{h.text_results.map((r) => <li key={r.date} className="tnum">{formatDate(r.date)}: {r.text}</li>)}</ul>
      </div>
    );
  }
  const lastTier = tierOf(tiers, last.value, last.unit);
  const status = lastTier ? lastTier.label : last.out_of_range ? t("charts.statusOut") : last.ref_min === null ? t("charts.statusNoRange") : t("charts.statusIn");
  const caption = buildCaption(i18n, h.display_name, unit(h.unit), points, todayMs);

  return (
    <div className="space-y-8">
      <p className="max-w-prose text-base text-muted-foreground" data-testid="history-caption">{caption}</p>
      <MarkerExplanation markerKey={h.marker_key} />
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div className="text-5xl font-semibold tnum font-heading">{num(last.value)} <span className="text-xl font-normal text-muted-foreground">{unit(h.unit)}</span></div>
        <Badge variant={last.out_of_range ? "destructive" : "secondary"}>{status}</Badge>
        {last.is_demo && <DemoBadge />}
        <span className="text-sm text-muted-foreground tnum">{tp("charts.resultsLatest", points.length, { date: formatDate(last.date) })}</span>
        <StartCourse markerKey={h.marker_key} markerName={h.display_name} />
      </div>
      <FreshnessLine markerKey={h.marker_key} />
      {points.some((p) => p.is_demo) && <p className="rounded-xl border border-data/40 p-3 text-sm">{t("charts.demoNote")}</p>}
      {h.unit_mismatch && <p role="alert" className="rounded-xl border border-outrange/50 p-3 text-sm">{t("charts.unitMismatch")}</p>}
      {h.range_mismatch && <p role="alert" className="rounded-xl border border-warn/60 p-3 text-sm">{t("charts.rangeMismatch")}</p>}
      <section className="space-y-4 rounded-xl border bg-card p-4 shadow-card sm:p-5">
        <PeriodSelector value={period} onChange={setPeriod} minDate={points[0].date} maxDate={todayIso} />
        <Tabs defaultValue="values">
          <TabsList><TabsTrigger value="values">{t("charts.tabValues")}</TabsTrigger><TabsTrigger value="range">{t("charts.tabRange")}</TabsTrigger></TabsList>
          <TabsContent value="values" className="pt-3"><TimeChart name={h.display_name} unit={h.unit} points={points} tiers={tiers} context={context} domain={domain} todayMs={todayMs} /></TabsContent>
          <TabsContent value="range" className="pt-3"><RangeOverlay h={h} others={others} domain={domain} todayMs={todayMs} /></TabsContent>
        </Tabs>
      </section>
      <MarkerCourses markerKey={h.marker_key} from={points[0].date} today={todayIso} />
      <DeltaTable h={h} />
      <ComparePanel h={h} />
    </div>
  );
}
