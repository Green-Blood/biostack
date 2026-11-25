"use client";
import Link from "next/link";
import { PencilLine } from "lucide-react";
import { buildCaption } from "@/components/charts/caption";
import { TimeChart, type ChartPoint } from "@/components/charts/time-chart";
import type { Domain } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { Context, OrganDetail, OrganSeries } from "@/lib/types";
import { capList, shownUnit, unverifiedPoints, type UnverifiedPoint } from "./table-model";

/** `staticMode` is the doctor/print rendering: no animation or hover, no edit links, one chart per row. */
type Props = { organ: OrganDetail; context: Context; domain: Domain; todayMs: number; staticMode?: boolean };

/** HistoryPoint-shaped points for one series; scans have no reference ranges, so nothing is ever "out of range". */
function toPoints(s: OrganSeries, suspect: Map<number, boolean>): ChartPoint[] {
  return s.points.filter((p) => p.value !== null).map((p) => ({
    date: p.date, value: p.value!, ref_min: null, ref_max: null, out_of_range: false,
    date_suspect: suspect.get(p.record_id) ?? false, unit: s.unit, is_demo: false,
  }));
}

/** Read together with the caption: which points of this chart are not verified, and where to check the latest one. */
function UnverifiedLine({ items, total, staticMode }: { items: UnverifiedPoint[]; total: number; staticMode: boolean }) {
  const { t, tp, formatDate } = useI18n();
  if (!items.length) return null;
  const latest = items.at(-1)!;
  return (
    <div className="flex gap-1.5 text-sm text-muted-foreground" data-testid="chart-unverified">
      <span aria-hidden className="font-semibold">?</span>
      <p className="min-w-0">
        {tp("organs.chartUnverified", items.length, { total })}{" "}
        <span className="italic tnum">{t("organs.chartUnverifiedDates", { dates: capList(items.map((p) => formatDate(p.date))) })}</span>{" "}
        {!staticMode && <Link href={`/records/${latest.record_id}`} className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
          <PencilLine aria-hidden className="size-3.5" />{t("organs.editNumbers")}
        </Link>}
      </p>
    </div>
  );
}

function SeriesCard({ s, title, points, unverified, context, domain, todayMs, staticMode }: { s: OrganSeries; title: string; points: ChartPoint[]; unverified: UnverifiedPoint[]; context: Context; domain: Domain; todayMs: number; staticMode: boolean }) {
  const i18n = useI18n();
  const { t, unit } = i18n;
  const u = unit(shownUnit(s.unit));
  return (
    <article className="surface min-w-0 space-y-2 p-4">
      <h3 className="font-sans text-base font-semibold leading-snug">
        {title}{u && <span className="ml-1.5 text-sm font-normal text-muted-foreground">{u}</span>}
      </h3>
      <p className="text-sm text-muted-foreground">
        {points.length >= 3 ? buildCaption(i18n, title, u, points, todayMs) : t("organs.tooLittleData")}
      </p>
      <UnverifiedLine items={unverified} total={points.length} staticMode={staticMode} />
      <TimeChart name={title} unit={shownUnit(s.unit)} points={points} tiers={[]} context={context} domain={domain} todayMs={todayMs} staticMode={staticMode} />
    </article>
  );
}

export function SeriesCharts({ organ, context, domain, todayMs, staticMode = false }: Props) {
  const { t } = useI18n();
  const suspect = new Map(organ.scans.map((s) => [s.record_id, s.date_suspect]));
  const sideOf = new Map(organ.params.map((p) => [p.series_key, p.side]));
  const titleOf = (s: OrganSeries) => {
    const side = sideOf.get(s.series_key);
    return side ? t("organs.seriesSide", { name: s.name, side: t(side === "left" ? "organs.sideLeft" : "organs.sideRight") }) : s.name;
  };
  const cards = organ.series.map((s) => ({ s, unverified: unverifiedPoints(organ, s) }));
  return (
    <div className="space-y-3">
      {cards.some((c) => c.unverified.length > 0) && (
        <p className="flex gap-1.5 rounded-xl border border-dashed p-3 text-sm text-muted-foreground" data-testid="charts-unverified-note">
          <span aria-hidden className="font-semibold">?</span>{t("organs.chartsUnverifiedNote")}
        </p>
      )}
      <div className={staticMode ? "grid grid-cols-1 gap-4" : "grid grid-cols-1 gap-4 lg:grid-cols-2"}>
        {cards.map(({ s, unverified }) => (
          <SeriesCard key={s.series_key} s={s} title={titleOf(s)} points={toPoints(s, suspect)} unverified={unverified} context={context} domain={domain} todayMs={todayMs} staticMode={staticMode} />
        ))}
      </div>
    </div>
  );
}
