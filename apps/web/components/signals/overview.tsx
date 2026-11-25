"use client";
import Link from "next/link";
import { ArrowRight, HeartPulse } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import type { SignalsOverview as Overview } from "@/lib/types";
import { IMPORT_HREF, localDay } from "./format";
import { LastNightCard } from "./last-night";
import { SignalTile } from "./signal-tile";
import { StaleNote } from "./stale-note";

export { IMPORT_HREF };

/** The 30-day span every sparkline is drawn over, so the tiles line up: ends at the newest point of any tile. */
function sparkSpan(data: Overview): [string, string] | null {
  const last = data.tiles.flatMap((t) => t.spark.map((p) => p.date)).sort().at(-1);
  if (!last) return null;
  const end = new Date(`${last}T00:00:00Z`);
  const start = new Date(end.getTime() - 29 * 86_400_000);
  return [start.toISOString().slice(0, 10), last];
}

export function SignalsOverview({ data }: { data: Overview }) {
  const { t, formatDate } = useI18n();
  if (!data.has_data) {
    return (
      <section className="empty-state flex flex-col items-center gap-3 px-6 py-10 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary"><HeartPulse className="size-6" aria-hidden /></span>
        <h2 className="text-xl font-semibold">{t("signals.emptyTitle")}</h2>
        <p className="max-w-prose text-sm text-muted-foreground">{t("signals.emptyText")}</p>
        <Link href={IMPORT_HREF} className={buttonVariants({ size: "lg" })}>{t("signals.emptyAction")}<ArrowRight aria-hidden /></Link>
      </section>
    );
  }
  const span = sparkSpan(data);
  const imported = data.latest_import?.finished_at;
  return (
    <div className="space-y-8">
      {imported && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="tnum">{t("signals.importedOn", { date: formatDate(localDay(imported)) })}</span>
          <Link href={IMPORT_HREF} className="font-medium text-primary underline-offset-4 hover:underline">{t("signals.importNewer")}</Link>
        </p>
      )}
      <StaleNote freshness={data} />
      {data.last_night ? <LastNightCard night={data.last_night} /> : <p className="empty-state p-4 text-sm text-muted-foreground">{t("signals.lastNightNone")}</p>}
      <section aria-labelledby="tiles-title" className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="tiles-title" className="text-2xl font-semibold">{t("signals.tilesTitle")}</h2>
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <span aria-hidden className="inline-block h-2.5 w-5 rounded-sm" style={{ background: "color-mix(in oklab, var(--chart-1) 16%, transparent)" }} />
            {t("signals.bandLegend")}
          </p>
        </div>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.tiles.map((tile) => <SignalTile key={tile.key} tile={tile} days={span} freshness={data} />)}
        </ul>
      </section>
    </div>
  );
}
