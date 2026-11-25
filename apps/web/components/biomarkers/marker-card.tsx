"use client";
import Link from "next/link";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { DemoBadge } from "@/components/demo-badge";
import { RangeHint } from "@/components/profile/range-hint";
import { useI18n } from "@/lib/i18n/client";
import type { MarkerSummaryFull } from "@/lib/types";
import { RangeStrip } from "./range-strip";
import { Sparkline } from "./sparkline";
import { ageLabel, changeOf, describePosition, positionOf } from "./status";

export function MarkerValue({ m }: { m: MarkerSummaryFull }) {
  const { formatNumber, unit } = useI18n();
  const out = positionOf(m).out;
  return m.latest_value !== null
    ? <><span className={out ? "font-semibold text-outrange" : "font-semibold"}>{formatNumber(m.latest_value, { maximumFractionDigits: 4 })}</span> <span className="text-muted-foreground">{unit(m.unit)}</span></>
    : <span>{m.latest_text ?? "—"}</span>;
}

export function ChangeArrow({ m }: { m: MarkerSummaryFull }) {
  const { t, formatNumber } = useI18n();
  const change = changeOf(m);
  if (!change) return null;
  const pct = change.pct === null ? "" : `${change.pct > 0 ? "+" : ""}${formatNumber(change.pct, { maximumFractionDigits: 0 })}%`;
  const words = change.dir === "flat" ? t("biomarkers.changeFlat") : t(change.dir === "up" ? "biomarkers.changeUp" : "biomarkers.changeDown", { pct: pct.replace(/^[+-]/, "") || "—" });
  const trend = change.trend === "toward" ? `, ${t("biomarkers.changeTowards")}` : change.trend === "away" ? `, ${t("biomarkers.changeAway")}` : "";
  const Icon = change.dir === "up" ? ArrowUp : change.dir === "down" ? ArrowDown : Minus;
  const tone = change.trend === "toward" ? "text-ok" : change.trend === "away" ? "text-warn" : "text-muted-foreground";
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs tnum ${tone}`} title={words + trend} aria-label={words + trend}>
      <Icon className="size-3.5" aria-hidden />{pct}
    </span>
  );
}

export function MarkerCard({ m }: { m: MarkerSummaryFull }) {
  const i18n = useI18n();
  const { t, formatDate } = i18n;
  const pos = positionOf(m);
  const words = describePosition(i18n, pos);
  const due = m.retest_days !== null && m.age_days > m.retest_days;
  return (
    <li className="group relative flex flex-col gap-2 rounded-2xl border border-border bg-card p-3.5 shadow-card transition-shadow focus-within:ring-2 focus-within:ring-ring hover:shadow-md motion-reduce:transition-none">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/biomarkers/${encodeURIComponent(m.marker_key)}`} className="min-w-0 font-medium leading-snug underline-offset-4 outline-none after:absolute after:inset-0 after:rounded-2xl hover:underline focus-visible:underline">
          {m.display_name}
        </Link>
        {m.is_demo && <DemoBadge />}
      </div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 tnum">
        <span className="text-lg"><MarkerValue m={m} /></span>
        <ChangeArrow m={m} />
      </div>
      {m.latest_value !== null
        ? <RangeStrip value={m.latest_value} min={m.ref_min} max={m.ref_max} tiers={m.tiers} unit={m.unit} />
        : <span className="text-xs text-muted-foreground">{t("biomarkers.textNotPlotted")}</span>}
      {m.ref_min === null && m.ref_max === null && <RangeHint needs={m.needs_profile} />}
      {words && <p className={`text-xs ${pos.out ? "text-outrange" : "text-muted-foreground"}`}>{words}</p>}
      <div className="mt-auto flex items-end justify-between gap-2 pt-1">
        <div className="min-w-0 text-xs text-muted-foreground tnum">
          <span title={t("biomarkers.ageTitle", { date: formatDate(m.latest_date), days: m.retest_days ?? "—" })} className={due ? "text-warn" : ""}>{ageLabel(i18n, m.age_days)}</span>
          {due && <span className="block text-warn">{t("biomarkers.ageDue")}</span>}
        </div>
        <Sparkline values={m.spark} out={pos.out} />
      </div>
    </li>
  );
}
