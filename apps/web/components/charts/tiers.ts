import type { MarkerTier, TierName } from "@/lib/types";
import { unitsCompatible } from "./units";

/** Strokes and text: semantic tokens per tier; the tier label (words) always travels with the colour. */
export const TIER_COLOR: Record<TierName, string> = {
  deficient: "var(--outrange)",
  insufficient: "var(--warn)",
  normal: "var(--ok)",
  high: "var(--warn)",
  toxic: "var(--outrange)",
};

/** Fill of the "normal" tier (the soft in-range tint); the other tiers tint their own stroke colour. */
export const TIER_NORMAL_FILL = "var(--inrange)";

/** The unit the tiers are written in (null when the API did not say). */
export const tiersUnit = (tiers: MarkerTier[]): string | null => tiers.find((t) => t.unit)?.unit ?? null;

/** The tier a value falls in, but only among tiers whose unit matches `unit` (absent unit = compatible). */
export function tierOf(tiers: MarkerTier[], value: number, unit?: string | null): MarkerTier | undefined {
  return tiers.find((t) => unitsCompatible(t.unit, unit) && (t.min === null || value >= t.min) && (t.max === null || value <= t.max));
}
