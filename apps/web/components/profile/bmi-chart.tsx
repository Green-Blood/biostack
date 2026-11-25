"use client";
import { useMemo, useState } from "react";
import { DEFAULT_PERIOD, periodDomain, type Period } from "@/components/charts/period";
import { PeriodSelector } from "@/components/charts/period-selector";
import { TimeChart, type ChartPoint } from "@/components/charts/time-chart";
import { dayMs } from "@/components/charts/time-scale";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { BmiBandKey, BmiHistory, BmiStatus, BodyKind, BodyMeasurement, MarkerTier, TierName } from "@/lib/types";
import { metaOf } from "./body-kinds";

// Band keys use the marker chart's tier vocabulary so the same bands, colours and labels draw the BMI scale.
const TIER: Record<BmiBandKey, TierName> = { underweight: "insufficient", normal: "normal", overweight: "high", obese: "toxic" };
const BAND_LABEL: Record<BmiBandKey, Key> = { underweight: "profile.bandUnderweight", normal: "profile.bandNormal", overweight: "profile.bandOverweight", obese: "profile.bandObese" };

const point = (date: string, value: number, unit: string, out: boolean): ChartPoint => ({ date, value, ref_min: null, ref_max: null, out_of_range: out, date_suspect: false, unit, is_demo: false });

const NEED: Record<Exclude<BmiStatus, "ok">, Key> = {
  needs_height: "profile.needHeight", needs_weight: "profile.needWeight", needs_birth_date: "profile.needBirthDate", adult_only: "profile.adultOnly",
};

export function BmiChart({ history, weights, historyFailed, kind, extra, profileStatus }: { profileStatus: BmiStatus; history: BmiHistory | null; weights: BodyMeasurement[]; historyFailed: boolean; kind: BodyKind | null; extra: BodyMeasurement[] }) {
  const { t, tp, formatDate } = useI18n();
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const [today] = useState(todayIso);
  const [tab, setTab] = useState<string | null>(null);
  const [seenKind, setSeenKind] = useState<BodyKind | null>(null);
  // Picking a card on the page switches the chart to that kind (set during render, not in an effect).
  if (kind !== seenKind) { setSeenKind(kind); if (kind) setTab(kind); }
  const compKind = kind && extra.some((m) => m.kind === kind) ? kind : null;
  const compMeta = compKind ? metaOf(compKind) : null;
  const compPoints = useMemo(() => extra.filter((m) => m.kind === compKind).sort((a, b) => a.date.localeCompare(b.date)).map((m) => point(m.date, m.value, compMeta?.unit ?? "", false)), [extra, compKind, compMeta]);
  const todayMs = dayMs(today);

  // BMI is drawn only when both the profile and the history agree it can be calculated.
  const status: BmiStatus = profileStatus !== "ok" ? profileStatus : (history?.bmi_status ?? "ok");
  const bmiOk = status === "ok";
  const bmiPoints = useMemo(() => (bmiOk ? [...(history?.points ?? [])] : []).sort((a, b) => a.date.localeCompare(b.date)).map((p) => point(p.date, p.bmi, "kg/m²", p.category !== "normal")), [history, bmiOk]);
  const weightPoints = useMemo(() => [...weights].sort((a, b) => a.date.localeCompare(b.date)).map((m) => point(m.date, m.value, "kg", false)), [weights]);
  const tiers = useMemo<MarkerTier[]>(() => (bmiOk ? history?.bands ?? [] : []).map((b) => ({ tier: TIER[b.key], min: b.min, max: b.max, label: t(BAND_LABEL[b.key]), unit: "kg/m²" })), [history, bmiOk, t]);
  const all = weightPoints.length ? weightPoints : bmiPoints;
  const periodPoints = compPoints.length ? [...all, ...compPoints].sort((a, b) => a.date.localeCompare(b.date)) : all;
  const domain = useMemo(() => periodDomain(period, periodPoints.map((p) => dayMs(p.date)), todayMs), [period, periodPoints, todayMs]);

  if (!periodPoints.length && !historyFailed) return <p className="empty-state p-5 text-muted-foreground">{t("profile.chartNoWeights")}</p>;
  const n = weightPoints.length;
  const summary = n < 3 ? (n ? tp("profile.chartFew", n) : "") : t("profile.chartMany", { n, from: formatDate(weightPoints[0].date), to: formatDate(weightPoints[n - 1].date) });
  return (
    <div className="space-y-4">
      {historyFailed && <p role="alert" className="text-sm text-outrange">{t("profile.chartLoadFailed")}</p>}
      {periodPoints.length > 0 && <PeriodSelector value={period} onChange={setPeriod} minDate={periodPoints[0].date} maxDate={today} />}
      {periodPoints.length > 0 && (
        <Tabs value={tab && (tab === "bmi" || tab === "weight" || tab === compKind) ? tab : bmiPoints.length ? "bmi" : "weight"} onValueChange={(v) => setTab(String(v))}>
          <TabsList><TabsTrigger value="bmi">{t("profile.tabBmi")}</TabsTrigger><TabsTrigger value="weight">{t("profile.tabWeight")}</TabsTrigger>{compKind && compKind !== "weight" && compMeta && <TabsTrigger value={compKind}>{t(compMeta.label)}</TabsTrigger>}</TabsList>
          <TabsContent value="bmi" className="pt-3">
            {bmiPoints.length
              ? <TimeChart name={t("profile.tabBmi")} unit="kg/m²" points={bmiPoints} tiers={tiers} context={null} domain={domain} todayMs={todayMs} />
              : <p className="empty-state p-5 text-muted-foreground">{bmiOk ? t("profile.chartNeedHeight") : t(NEED[status as Exclude<BmiStatus, "ok">])}</p>}
            {history?.note && bmiPoints.length > 0 && <p className="mt-3 max-w-prose text-sm text-muted-foreground">{history.note}</p>}
          </TabsContent>
          <TabsContent value="weight" className="pt-3">
            <TimeChart name={t("profile.tabWeight")} unit="kg" points={weightPoints} tiers={[]} context={null} domain={domain} todayMs={todayMs} />
          </TabsContent>
          {compKind && compMeta && (
            <TabsContent value={compKind} className="pt-3">
              <TimeChart name={t(compMeta.label)} unit={compMeta.unit} points={compPoints} tiers={[]} context={null} domain={domain} todayMs={todayMs} />
              {compPoints.length < 3 && <p className="mt-3 text-sm text-muted-foreground">{tp("profile.compTooFew", compPoints.length)}</p>}
            </TabsContent>
          )}
        </Tabs>
      )}
      {summary && <p className="max-w-prose text-sm text-muted-foreground">{summary}</p>}
    </div>
  );
}
