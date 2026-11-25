import Link from "next/link";
import { ArrowUpRight, CircleAlert } from "lucide-react";
import { RangeStrip } from "@/components/biomarkers/range-strip";
import type { OverviewMarker } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { SectionHeader } from "./section-header";

const MAX_ROWS = 12;

/** Markers whose own latest result is out of range, each with its value, result date, reference and range strip. */
export async function AttentionBlock({ markers }: { markers: OverviewMarker[] }) {
  const { t, formatNumber, formatDate, unit } = await getI18n();
  const num = (v: number) => formatNumber(v, { maximumFractionDigits: 4 });
  const reference = (m: OverviewMarker) =>
    m.ref_min !== null && m.ref_max !== null ? t("overview.refBetween", { min: num(m.ref_min), max: num(m.ref_max) })
      : m.ref_max !== null ? t("overview.refUpTo", { max: num(m.ref_max) })
        : m.ref_min !== null ? t("overview.refFrom", { min: num(m.ref_min) })
          : t("overview.refNone");
  // One plain sentence: which side of normal, and by how much.
  const verdict = (m: OverviewMarker) => {
    const u = unit(m.unit);
    if (m.ref_max !== null && m.latest_value! > m.ref_max) return t("overview.verdictAbove", { delta: `${num(m.latest_value! - m.ref_max)} ${u}`.trim() });
    if (m.ref_min !== null && m.latest_value! < m.ref_min) return t("overview.verdictBelow", { delta: `${num(m.ref_min - m.latest_value!)} ${u}`.trim() });
    return t("overview.verdictOutside");
  };
  const shown = markers.slice(0, MAX_ROWS);
  const dates = new Set(markers.map((m) => m.latest_date));
  // "Report of <date>" is only honest when every row comes from the same day.
  const sub = dates.size === 1 ? t("overview.attentionSub", { date: formatDate([...dates][0]) }) : t("overview.attentionSubMixed");
  const resultDate = (m: OverviewMarker) => formatDate(m.latest_date, { day: "numeric", month: "short", year: "numeric" });

  return (
    <section aria-labelledby="out-h">
      <SectionHeader id="out-h" title={t("overview.attentionHeading")} sub={sub} />
      {markers.length === 0 ? (
        <p className="empty-state flex items-center gap-3 p-5 text-muted-foreground"><span className="size-2.5 shrink-0 rounded-full bg-ok" aria-hidden />{t("overview.attentionNone")}</p>
      ) : (
        <ul className="surface divide-y overflow-hidden border-l-4 border-l-outrange">
          {shown.map((m) => (
            <li key={m.marker_key}>
              <Link href={`/biomarkers/${encodeURIComponent(m.marker_key)}`} className="group grid grid-cols-[1fr_auto] items-start gap-x-6 gap-y-3 px-4 py-4 transition-colors hover:bg-accent/50 sm:grid-cols-[minmax(10rem,13rem)_minmax(7rem,9rem)_1fr_auto]">
                <span className="min-w-0">
                  <span className="flex items-center gap-2 font-medium"><CircleAlert className="size-4 shrink-0 text-outrange" aria-hidden />{m.display_name}</span>
                  <span className="mt-0.5 block pl-6 text-xs text-muted-foreground">{t("overview.resultOn", { date: resultDate(m) })}</span>
                </span>
                <span className="tnum text-right sm:text-left"><span className="text-2xl font-semibold leading-none text-outrange">{num(m.latest_value!)}</span> <span className="text-sm text-muted-foreground">{unit(m.unit)}</span></span>
                <span className="col-span-2 min-w-0 sm:col-span-1">
                  <span className="block text-sm font-medium text-outrange">{verdict(m)}</span>
                  <span className="mb-1 block text-xs text-muted-foreground tnum">{reference(m)}</span>
                  <RangeStrip value={m.latest_value!} min={m.ref_min} max={m.ref_max} unit={m.unit} />
                </span>
                <ArrowUpRight className="hidden size-4 text-muted-foreground transition-colors group-hover:text-foreground sm:block" aria-hidden />
              </Link>
            </li>
          ))}
          {markers.length > MAX_ROWS && (
            <li className="px-4 py-3 text-sm text-muted-foreground">
              <Link href="/biomarkers" className="underline underline-offset-4">{t("overview.moreOut", { n: markers.length - MAX_ROWS })}</Link>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
