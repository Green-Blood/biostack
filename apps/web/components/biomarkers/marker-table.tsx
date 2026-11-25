"use client";
import Link from "next/link";
import { DemoBadge } from "@/components/demo-badge";
import type { MarkerSummaryFull } from "@/lib/types";
import { MarkerValue } from "./marker-card";
import { RangeStrip } from "./range-strip";
import { Sparkline } from "./sparkline";
import { positionOf } from "./status";
import { useI18n } from "@/lib/i18n/client";

/** The flat alternative view: every marker as one row. */
export function MarkerTable({ rows }: { rows: MarkerSummaryFull[] }) {
  const { t, tp, formatDate } = useI18n();
  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">{t("biomarkers.colMarker")}</th>
            <th className="px-4 py-2.5 text-right font-medium whitespace-nowrap">{t("biomarkers.colLatest")}</th>
            <th className="px-4 py-2.5 font-medium">{t("biomarkers.colRange")}</th>
            <th className="px-4 py-2.5 font-medium">{t("biomarkers.colHistory")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.marker_key} className="border-b last:border-0 hover:bg-accent/40">
              <td className="px-4 py-3">
                <Link href={`/biomarkers/${encodeURIComponent(m.marker_key)}`} className="rounded font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">{m.display_name}</Link>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground tnum"><span className="whitespace-nowrap">{formatDate(m.latest_date)}</span>{m.is_demo && <DemoBadge />}</div>
              </td>
              <td className="px-4 py-3 text-right tnum"><MarkerValue m={m} /></td>
              <td className="w-[34%] px-4 py-3">
                {m.latest_value !== null ? <RangeStrip value={m.latest_value} min={m.ref_min} max={m.ref_max} tiers={m.tiers} unit={m.unit} /> : <span className="text-xs text-muted-foreground">{t("biomarkers.textNotPlotted")}</span>}
              </td>
              <td className="px-4 py-3"><Sparkline values={m.spark} out={positionOf(m).out} /> <span className="ml-1 text-xs text-muted-foreground tnum">{m.count > 0 ? tp("biomarkers.resultsCount", m.count) : ""}</span></td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-muted-foreground">{t("biomarkers.noMatch")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
