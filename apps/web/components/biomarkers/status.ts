import type { ClientI18n } from "@/lib/i18n/client-core";
import type { Key } from "@/lib/i18n/translate";
import { tierOf } from "@/components/charts/tiers";
import type { MarkerSummaryFull, Tier, TierName } from "@/lib/types";

/** Display order of body systems; the API key is the identity, this is only the reading order. */
export const SYSTEM_ORDER = ["blood_count", "lipids", "glucose", "thyroid", "vitamins", "minerals", "liver", "kidney", "hormones", "inflammation", "coagulation", "pancreas", "other"] as const;

export const SYSTEM_LABEL: Record<string, Key> = {
  thyroid: "common.systemThyroid", liver: "common.systemLiver", lipids: "common.systemLipids", blood_count: "common.systemBloodCount",
  minerals: "common.systemMinerals", inflammation: "common.systemInflammation", hormones: "common.systemHormones",
  vitamins: "common.systemVitamins", glucose: "common.systemGlucose", coagulation: "common.systemCoagulation",
  kidney: "common.systemKidney", pancreas: "common.systemPancreas", other: "common.systemOther",
};

export const TIER_LABEL: Record<TierName, Key> = {
  deficient: "common.tierDeficient", insufficient: "common.tierInsufficient", normal: "common.tierNormal", high: "common.tierHigh", toxic: "common.tierToxic",
};

export { TIER_COLOR, TIER_NORMAL_FILL } from "@/components/charts/tiers";

export const normalizeText = (s: string) => s.toLowerCase().replace(/ё/g, "е");

/** The tier a value is in, only when the tier's unit matches the value's unit. */
export const tierAt = tierOf;

export type Position = {
  /** Where the latest value sits relative to the plain reference range (null when the marker has none). */
  side: "below" | "within" | "above" | null;
  tier: Tier | undefined;
  out: boolean;
  near: boolean;
  /** 0 inside the range; otherwise how far outside, in widths of the range. Used only to order markers. */
  deviation: number;
};

export function positionOf(m: Pick<MarkerSummaryFull, "latest_value" | "ref_min" | "ref_max" | "tiers" | "out_of_range_latest" | "unit">): Position {
  const v = m.latest_value;
  if (v === null) return { side: null, tier: undefined, out: false, near: false, deviation: 0 };
  const { ref_min: lo, ref_max: hi } = m;
  const width = lo !== null && hi !== null && hi > lo ? hi - lo : Math.abs(hi ?? lo ?? v) || 1;
  const side = lo === null && hi === null ? null : lo !== null && v < lo ? "below" : hi !== null && v > hi ? "above" : "within";
  const gap = side === "below" ? lo! - v : side === "above" ? v - hi! : 0;
  const tier = tierAt(m.tiers, v, m.unit);
  const tierOut = tier !== undefined && tier.tier !== "normal";
  const out = m.out_of_range_latest || side === "below" || side === "above" || tierOut;
  return { side, tier, out, near: side !== "within" && side !== null && gap / width < 0.1, deviation: out ? Math.max(gap / width, 0.001) : 0 };
}

export function formatBand(t: ClientI18n["t"], fmt: (n: number) => string, tier: Tier): string {
  if (tier.min !== null && tier.max !== null) return t("biomarkers.rangeBetween", { min: fmt(tier.min), max: fmt(tier.max) });
  if (tier.max !== null) return t("biomarkers.rangeLess", { value: fmt(tier.max) });
  if (tier.min !== null) return t("biomarkers.rangeMore", { value: fmt(tier.min) });
  return "";
}

/** One plain sentence about where the value sits, from the lab's tiers or reference range, never from the AI. */
export function describePosition(i18n: ClientI18n, p: Position): string | null {
  const { t, formatNumber } = i18n;
  const fmt = (n: number) => formatNumber(n, { maximumFractionDigits: 4 });
  if (p.tier && p.tier.tier !== "normal") {
    const range = formatBand(t, fmt, p.tier);
    const tier = t(TIER_LABEL[p.tier.tier]);
    return range ? t("biomarkers.posTier", { tier, range }) : t("biomarkers.posTierNoRange", { tier });
  }
  if (p.side === null) return null;
  if (p.side === "within") return t("biomarkers.posWithin");
  if (p.side === "below") return t(p.near ? "biomarkers.posBelowNear" : "biomarkers.posBelow");
  return t(p.near ? "biomarkers.posAboveNear" : "biomarkers.posAbove");
}

export type Change = { pct: number | null; dir: "up" | "down" | "flat"; trend: "toward" | "away" | "neutral" };

/** Change of the latest result against the one before it, from the spark values (oldest first). */
export function changeOf(m: Pick<MarkerSummaryFull, "spark" | "ref_min" | "ref_max">): Change | null {
  if (m.spark.length < 2) return null;
  const last = m.spark[m.spark.length - 1], prev = m.spark[m.spark.length - 2];
  const diff = last - prev;
  const dir = Math.abs(diff) < 1e-9 ? "flat" : diff > 0 ? "up" : "down";
  const dist = (v: number) => Math.max((m.ref_min ?? -Infinity) - v, v - (m.ref_max ?? Infinity), 0);
  const hasRange = m.ref_min !== null || m.ref_max !== null;
  const trend = !hasRange || dir === "flat" ? "neutral" : dist(last) < dist(prev) ? "toward" : dist(last) > dist(prev) ? "away" : "neutral";
  return { pct: prev !== 0 ? (diff / Math.abs(prev)) * 100 : null, dir, trend };
}

export function ageLabel(i18n: ClientI18n, days: number): string {
  const { tp, t } = i18n;
  if (days < 1) return t("biomarkers.ageToday");
  if (days < 60) return tp("biomarkers.ageDays", days);
  if (days < 730) return tp("biomarkers.ageMonths", Math.round(days / 30.44));
  return tp("biomarkers.ageYears", Math.round(days / 365.25));
}

/** Deviation first, then name; a marker with no result sorts last. */
export const byAttention = (a: MarkerSummaryFull, b: MarkerSummaryFull) =>
  positionOf(b).deviation - positionOf(a).deviation || a.display_name.localeCompare(b.display_name);
