import Link from "next/link";
import { ArrowRight, Footprints, HeartPulse, Moon, Waves, type LucideIcon } from "lucide-react";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { Key } from "@/lib/i18n/translate";
import type { SignalTileKey, SignalsOverview } from "@/lib/types";
import { duration, TILE_HREF, tileEmptyText, tileValue } from "@/components/signals/format";
import { StaleNote } from "@/components/signals/stale-note";
import { SectionHeader } from "./section-header";

const SHOWN: { key: SignalTileKey; icon: LucideIcon }[] = [
  { key: "resting_hr", icon: HeartPulse }, { key: "hrv_sdnn", icon: Waves }, { key: "steps", icon: Footprints },
];
const POSITION: Record<string, Key> = { below: "signals.positionBelow", within: "signals.positionWithin", above: "signals.positionAbove" };

/** The latest night and day values from the watch, linking into Body signals; says how old they are when the data is
 *  stale. Renders nothing without watch data or when the API cannot answer. */
export async function SignalsStrip() {
  const data = await apiGet<SignalsOverview>("signals/overview").catch(() => null);
  if (!data?.has_data) return null;
  const i18n = await getI18n();
  const { t, formatDate } = i18n;
  const night = data.last_night;
  const cell = "surface surface-interactive flex min-w-0 flex-col gap-1 p-4 outline-none focus-visible:ring-2 focus-visible:ring-ring";
  const head = (Icon: LucideIcon, name: string, date: string | null) => (
    <span className="flex items-baseline justify-between gap-2 text-sm text-muted-foreground">
      <span className="flex min-w-0 items-center gap-1.5 font-medium"><Icon className="size-4 shrink-0 self-center" aria-hidden /><span className="truncate">{name}</span></span>
      {date && <span className="shrink-0 text-xs tnum">{formatDate(date, { day: "numeric", month: "short" })}</span>}
    </span>
  );
  return (
    <section aria-labelledby="signals-strip-h">
      <SectionHeader id="signals-strip-h" title={t("heart.stripTitle")} action={
        <Link href="/signals" className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">{t("signals.openSignals")}<ArrowRight className="size-3.5" aria-hidden /></Link>
      } />
      <StaleNote freshness={data} className="mb-3" />
      {data.short_sleep_end && <p className="surface mb-3 p-4 text-sm">{t("signals.shortSleepInsight", {
        date: formatDate(data.short_sleep_end, { day: "numeric", month: "short" }),
      })}</p>}
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <li className="flex">
          <Link href="/signals/sleep" className={`${cell} flex-1`}>
            {head(Moon, t("signals.lastNightTitle"), night?.wake_date ?? null)}
            {night ? (
              <span className="tnum" aria-label={`${t("signals.asleepLabel")}: ${duration(i18n, night.duration_min).long}`}>
                <span className="text-2xl font-semibold tracking-tight">{duration(i18n, night.duration_min).short}</span>
                <span className="ml-1 text-sm text-muted-foreground">{t("signals.hoursUnit")}</span>
              </span>
            ) : <span className="text-sm text-muted-foreground">{t("signals.noData")}</span>}
          </Link>
        </li>
        {SHOWN.map(({ key, icon }) => {
          const tile = data.tiles.find((x) => x.key === key);
          if (!tile) return null;
          const v = tile.value !== null ? tileValue(i18n, key, tile.value, tile.unit) : null;
          return (
            <li key={key} className="flex">
              <Link href={TILE_HREF[key]} className={`${cell} flex-1`}>
                {head(icon, tile.name, tile.date)}
                {v ? (
                  <span className="tnum" aria-label={v.spoken}>
                    <span className="text-2xl font-semibold tracking-tight">{v.text}</span>
                    {v.unit && <span className="ml-1 text-sm text-muted-foreground">{v.unit}</span>}
                  </span>
                ) : <span className="text-sm text-muted-foreground">{tileEmptyText(i18n, tile.spark.length > 0, data)}</span>}
                {tile.position ? <span className="text-xs text-muted-foreground">{t(POSITION[tile.position])}</span>
                  : v && tile.partial && <span className="text-xs text-muted-foreground">{t("signals.partialDay")}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
