import type { MarkerTier } from "@/lib/types";
import type { ClientI18n } from "@/lib/i18n/client-core";
import { TIER_COLOR, TIER_NORMAL_FILL } from "./tiers";
import type { Plot } from "./time-axis";

export function tierRangeText(i18n: ClientI18n, tier: Pick<MarkerTier, "min" | "max">): string {
  const n = (v: number) => i18n.formatNumber(v, { maximumFractionDigits: 2 });
  if (tier.min !== null && tier.max !== null) return `${n(tier.min)}–${n(tier.max)}`;
  if (tier.min !== null) return i18n.t("charts.tierFrom", { value: n(tier.min) });
  if (tier.max !== null) return i18n.t("charts.tierTo", { value: n(tier.max) });
  return "";
}

/**
 * Tinted bands across the plot: one per tier when the marker has tiers (in the tiers' own unit), otherwise the plain reference range.
 * Each band is labelled in words, so meaning never rests on colour alone.
 */
export function Bands({ y, plot, tiers, refRange: ref, i18n, usual = false }: {
  y: (v: number) => number; plot: Plot; tiers: MarkerTier[]; refRange: { min: number | null; max: number | null } | null; i18n: ClientI18n;
  /** The band is the owner's own usual range (a neutral tint), not a reference range. */
  usual?: boolean;
}) {
  const w = plot.right - plot.left;
  const clampY = (v: number) => Math.min(plot.bottom, Math.max(plot.top, v));
  if (tiers.length) {
    return (
      <g aria-hidden="true">
        {tiers.map((tier) => {
          const yTop = clampY(tier.max === null ? plot.top : y(tier.max));
          const yBottom = clampY(tier.min === null ? plot.bottom : y(tier.min));
          const h = yBottom - yTop;
          if (h <= 0.5) return null;
          const color = TIER_COLOR[tier.tier];
          return (
            <g key={tier.tier + tier.label}>
              <rect x={plot.left} y={yTop} width={w} height={h} style={{ fill: tier.tier === "normal" ? TIER_NORMAL_FILL : color }} fillOpacity={tier.tier === "normal" ? 0.85 : 0.1} />
              <line x1={plot.left} x2={plot.right} y1={yTop} y2={yTop} stroke={color} strokeOpacity={0.35} strokeDasharray="3 3" />
              {h >= 16 && <text x={plot.left + 6} y={yTop + 12} className="fill-muted-foreground text-[10px]">{tier.label} {tierRangeText(i18n, tier)}</text>}
            </g>
          );
        })}
      </g>
    );
  }
  if (ref && (ref.min !== null || ref.max !== null)) {
    const yTop = clampY(ref.max === null ? plot.top : y(ref.max));
    const yBottom = clampY(ref.min === null ? plot.bottom : y(ref.min));
    const h = yBottom - yTop;
    if (h <= 0.5) return null;
    return (
      <g aria-hidden="true">
        <rect x={plot.left} y={yTop} width={w} height={h} style={{ fill: usual ? "color-mix(in oklab, var(--chart-1) 14%, transparent)" : "var(--inrange)" }} fillOpacity={usual ? 1 : 0.85} />
        {h >= 16 && <text x={plot.left + 6} y={yTop + 12} className="fill-muted-foreground text-[10px]">{i18n.t(usual ? "charts.usualBand" : "charts.refBand", { range: tierRangeText(i18n, { min: ref.min, max: ref.max }) })}</text>}
      </g>
    );
  }
  return null;
}
