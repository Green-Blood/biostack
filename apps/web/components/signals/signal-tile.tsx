"use client";
import Link from "next/link";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { Sparkline } from "@/components/profile/sparkline";
import { useI18n } from "@/lib/i18n/client";
import type { SignalFreshness, SignalPosition, SignalTile as Tile } from "@/lib/types";
import { TILE_HREF, tileEmptyText, tileValue } from "./format";

const POSITION = {
  below: { key: "signals.positionBelow", icon: ArrowDown },
  within: { key: "signals.positionWithin", icon: Minus },
  above: { key: "signals.positionAbove", icon: ArrowUp },
} as const;

/** Where the value sits against the owner's usual range, in words. Deliberately neutral: no good/bad colour. */
export function PositionWords({ position }: { position: SignalPosition }) {
  const { t } = useI18n();
  const { key, icon: Icon } = POSITION[position];
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground">
      <Icon className="size-3.5" aria-hidden />{t(key)}
    </span>
  );
}

export function SignalTile({ tile, days, freshness }: { tile: Tile; days: [string, string] | null; freshness: SignalFreshness }) {
  const i18n = useI18n();
  const { t, formatDate } = i18n;
  const stale = freshness.stale && freshness.as_of ? formatDate(freshness.as_of, { day: "numeric", month: "short", year: "numeric" }) : null;
  const shown = tile.value !== null ? tileValue(i18n, tile.key, tile.value, tile.unit) : null;
  const range = tile.band
    ? t("signals.usualRange", { lo: tileValue(i18n, tile.key, tile.band.p25, tile.unit).text, hi: tileValue(i18n, tile.key, tile.band.p75, tile.unit).text })
    : null;
  return (
    <li className="surface surface-interactive group relative flex min-w-0 flex-col gap-2 p-4 focus-within:ring-2 focus-within:ring-ring motion-reduce:transition-none">
      <div className="flex items-baseline justify-between gap-2">
        <Link href={TILE_HREF[tile.key]} aria-label={t("signals.openTile", { name: tile.name })}
          className="min-w-0 break-words text-sm font-medium text-muted-foreground underline-offset-4 outline-none after:absolute after:inset-0 after:rounded-[inherit] hover:underline focus-visible:underline">
          {tile.name}
        </Link>
        {tile.date && <span className="shrink-0 text-xs text-muted-foreground tnum">{formatDate(tile.date, { day: "numeric", month: "short" })}</span>}
      </div>
      {shown ? (
        <p className="tnum" aria-label={shown.spoken}>
          <span className="text-3xl font-semibold tracking-tight">{shown.text}</span>
          {shown.unit && <span className="ml-1.5 text-sm text-muted-foreground">{shown.unit}</span>}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">{tileEmptyText(i18n, tile.spark.length > 0, freshness)}</p>
      )}
      {tile.spark.length > 0 && (
        <Sparkline points={tile.spark} band={tile.band} days={days ?? undefined} label={stale ? t("signals.sparkLabelTo", { name: tile.name, date: stale }) : t("signals.sparkLabel", { name: tile.name })} />
      )}
      <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-1">
        {tile.position ? <PositionWords position={tile.position} />
          : shown && <span className="text-xs text-muted-foreground">{t(tile.partial ? "signals.partialDay" : "signals.noBand")}</span>}
        {range && <span className="text-xs text-muted-foreground tnum">{range}</span>}
      </div>
    </li>
  );
}
