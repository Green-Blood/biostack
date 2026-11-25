"use client";
import { useI18n } from "@/lib/i18n/client";
import type { Tier } from "@/lib/types";
import { TIER_COLOR, TIER_NORMAL_FILL, tierAt } from "./status";
import { unitsCompatible } from "@/components/charts/units";

/** A value shown against the lab's tiers when it printed any, else against its plain reference range. */
export function RangeStrip({ value, min, max, tiers: allTiers = [], unit, labels = true, className = "" }: { value: number; min: number | null; max: number | null; tiers?: Tier[]; unit?: string; labels?: boolean; className?: string }) {
  const { t, formatNumber } = useI18n();
  // Tiers printed in another unit would misjudge this value: ignore them and fall back to the plain range.
  const tiers = allTiers.filter((x) => unitsCompatible(x.unit, unit));
  const hasTiers = tiers.length > 0;
  if (!hasTiers && min === null && max === null) return <span className="text-xs text-muted-foreground">{t("biomarkers.noRange")}</span>;

  const bounds = hasTiers ? tiers.flatMap((x) => [x.min, x.max]).filter((n): n is number => n !== null) : [min, max].filter((n): n is number => n !== null);
  const lo = bounds.length ? Math.min(...bounds) : value, hi = bounds.length ? Math.max(...bounds) : value;
  const span = Math.max(hi - lo, Math.abs(hi) * 0.2, 1e-9);
  const d0 = Math.min(lo, value) - span * 0.35, d1 = Math.max(hi, value) + span * 0.35;
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - d0) / (d1 - d0)) * 100));

  const bands = hasTiers
    ? tiers.map((x) => ({ from: x.min ?? d0, to: x.max ?? d1, color: TIER_COLOR[x.tier], normal: x.tier === "normal" }))
    : [{ from: min ?? d0, to: max ?? d1, color: TIER_COLOR.normal, normal: true }];
  const tier = hasTiers ? tierAt(tiers, value) : undefined;
  const out = hasTiers && tier ? tier.tier !== "normal" : (min !== null && value < min) || (max !== null && value > max);
  const v = formatNumber(value, { maximumFractionDigits: 4 });
  const below = tier ? tier.tier === "deficient" || tier.tier === "insufficient" : min !== null && value < min;
  const label = out ? (below ? t("biomarkers.rangeBelow", { value: v }) : t("biomarkers.rangeAbove", { value: v })) : t("biomarkers.rangeWithin", { value: v });
  // Numbers under the bar: every distinct band edge, skipping labels that would collide.
  const edges = [...new Set(bounds)].sort((x, y) => x - y).reduce<number[]>((kept, n) => (kept.length && pct(n) - pct(kept[kept.length - 1]) < 14 ? kept : [...kept, n]), []);
  const clamp = (n: number) => Math.min(94, Math.max(6, n));
  return (
    <div className={`w-full min-w-28 ${className}`} role="img" aria-label={label}>
      {labels && (
        <div className="relative h-5 text-xs font-semibold tnum">
          <span className={`absolute -translate-x-1/2 whitespace-nowrap ${out ? "text-outrange" : "text-foreground"}`} style={{ left: `${clamp(pct(value))}%` }}>{v}</span>
        </div>
      )}
      <div className="relative h-4">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {bands.map((b, i) => (
          <div key={i} className="absolute top-1/2 h-3 -translate-y-1/2 rounded-sm"
            style={{ left: `${pct(b.from)}%`, width: `${Math.max(pct(b.to) - pct(b.from), 0.5)}%`, background: b.normal ? TIER_NORMAL_FILL : `color-mix(in oklab, ${b.color} 45%, transparent)` }} />
        ))}
        <div className={`absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background shadow-sm ${out ? "bg-outrange" : "bg-data"}`} style={{ left: `${pct(value)}%` }} />
      </div>
      {labels && (
        <div className="relative h-4 text-[11px] text-muted-foreground tnum">
          {edges.map((n) => (
            <span key={n} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${clamp(pct(n))}%` }}>{formatNumber(n, { maximumFractionDigits: 4 })}</span>
          ))}
        </div>
      )}
    </div>
  );
}
