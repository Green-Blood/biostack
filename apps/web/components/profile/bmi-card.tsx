"use client";
import { TIER_COLOR, TIER_NORMAL_FILL } from "@/components/charts/tiers";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { BmiStatus, Profile } from "@/lib/types";
import { CATEGORY_KEY } from "./category";

const NEED: Record<Exclude<BmiStatus, "ok">, Key> = {
  needs_height: "profile.needHeight", needs_weight: "profile.needWeight", needs_birth_date: "profile.needBirthDate", adult_only: "profile.adultOnly",
};
// WHO adult bands drawn on a fixed 15 to 40 scale; a value outside is pinned to the edge.
const LO = 15, HI = 40;
const EDGES = [18.5, 25, 30];
const BANDS = [
  { from: LO, to: 18.5, color: TIER_COLOR.insufficient, normal: false },
  { from: 18.5, to: 25, color: TIER_COLOR.normal, normal: true },
  { from: 25, to: 30, color: TIER_COLOR.high, normal: false },
  { from: 30, to: HI, color: TIER_COLOR.toxic, normal: false },
];
const pct = (v: number) => Math.min(100, Math.max(0, ((v - LO) / (HI - LO)) * 100));

export function BmiCard({ profile }: { profile: Profile }) {
  const { t, formatNumber, formatDate } = useI18n();
  const bmi = profile.bmi;
  if (profile.bmi_status !== "ok" || !bmi) {
    const status = profile.bmi_status === "ok" ? "needs_weight" : profile.bmi_status;
    return <p className="empty-state p-5 text-muted-foreground">{t(NEED[status])}</p>;
  }
  const v = formatNumber(bmi.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const category = t(CATEGORY_KEY[bmi.category]);
  const out = bmi.category !== "normal";
  const clamp = (n: number) => Math.min(94, Math.max(6, n));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="font-heading text-5xl font-semibold tnum">{v} <span className="text-lg font-normal text-muted-foreground">{t("profile.bmiUnit")}</span></p>
        <p className="text-lg font-medium">{category}</p>
      </div>
      <div className="max-w-xl" role="img" aria-label={t("profile.scaleLabel", { value: v, category })}>
        <div className="relative h-5 text-xs font-semibold tnum">
          <span className={`absolute -translate-x-1/2 whitespace-nowrap ${out ? "text-outrange" : "text-foreground"}`} style={{ left: `${clamp(pct(bmi.value))}%` }}>{v}</span>
        </div>
        <div className="relative h-4">
          <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
          {BANDS.map((b) => (
            <div key={b.from} className="absolute top-1/2 h-3 -translate-y-1/2 rounded-sm" style={{ left: `${pct(b.from)}%`, width: `${pct(b.to) - pct(b.from)}%`, background: b.normal ? TIER_NORMAL_FILL : `color-mix(in oklab, ${b.color} 45%, transparent)` }} />
          ))}
          <div className={`absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background shadow-sm ${out ? "bg-outrange" : "bg-data"}`} style={{ left: `${pct(bmi.value)}%` }} />
        </div>
        <div className="relative h-4 text-[11px] text-muted-foreground tnum">
          {EDGES.map((n) => <span key={n} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${pct(n)}%` }}>{formatNumber(n, { maximumFractionDigits: 1 })}</span>)}
        </div>
      </div>
      <p className="text-sm text-muted-foreground tnum">{t("profile.bmiBasedOn", { date: formatDate(bmi.date) })}</p>
      <p className="max-w-prose text-sm text-muted-foreground">{t("profile.bmiCaveat")}</p>
    </div>
  );
}
