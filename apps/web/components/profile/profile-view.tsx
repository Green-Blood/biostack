"use client";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson } from "@/lib/request";
import type { BmiHistory, BodyKind, BodyMeasurement, BodySnapshot, Measurement, Profile } from "@/lib/types";
import { BasicsForm } from "./basics-form";
import { BmiCard } from "./bmi-card";
import { BmiChart } from "./bmi-chart";
import { BodyCard } from "./body-card";
import { CompositionCards } from "./composition-cards";
import { RefillCard } from "./refill-card";
import { ScalesCard } from "./scales-card";
import { MeasurementsList } from "./measurements-list";

export type ProfileData = { profile: Profile | null; weights: Measurement[]; waists: Measurement[]; history: BmiHistory | null; body: BodySnapshot | null; measurements: BodyMeasurement[] | null };

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="surface min-w-0 space-y-4 p-4 sm:p-5">
      <h2 id={id} className="text-2xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function ProfileView({ initial }: { initial: ProfileData }) {
  const { t } = useI18n();
  const [data, setData] = useState(initial);
  const [selected, setSelected] = useState<BodyKind | null>(null);
  const [loading, setLoading] = useState(false);

  const requestId = useRef(0);
  const reload = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    const [profile, weights, waists, history, body, measurements] = await Promise.allSettled([
      getJson<Profile>("profile"), getJson<Measurement[]>("profile/measurements?kind=weight"),
      getJson<Measurement[]>("profile/measurements?kind=waist"), getJson<BmiHistory>("profile/bmi-history"),
      getJson<BodySnapshot>("profile/body"), getJson<BodyMeasurement[]>("profile/measurements"),
    ]);
    if (id !== requestId.current) return; // a newer reload is in flight or done; this answer is stale
    setData((prev) => ({
      profile: profile.status === "fulfilled" ? profile.value : prev.profile,
      weights: weights.status === "fulfilled" ? weights.value : prev.weights,
      waists: waists.status === "fulfilled" ? waists.value : prev.waists,
      history: history.status === "fulfilled" ? history.value : null,
      body: body.status === "fulfilled" ? body.value : prev.body,
      measurements: measurements.status === "fulfilled" ? measurements.value : prev.measurements,
    }));
    setLoading(false);
  }, []);

  const p = data.profile;
  // The full list when the API gave it; otherwise the weight and waist rows loaded on their own.
  const rows: BodyMeasurement[] = data.measurements ?? [...data.weights, ...data.waists];
  const pickKind = (k: BodyKind) => {
    setSelected(k);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById("chart-h")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
  };
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="font-semibold">{t("profile.title")}</h1>
        <p className="max-w-prose text-muted-foreground">{t("profile.intro")}</p>
      </header>

      <section aria-labelledby="uses-h" className="surface max-w-prose space-y-2 p-4 text-sm sm:p-5">
        <h2 id="uses-h" className="text-lg font-semibold">{t("profile.usesTitle")}</h2>
        <p className="text-muted-foreground">{t("profile.usesRanges")}</p>
        <p className="text-muted-foreground">{t("profile.usesAi")}</p>
        <Link href="/settings#ai" className="inline-block font-medium text-primary underline-offset-4 hover:underline">{t("profile.usesSettings")}</Link>
      </section>

      {!p ? (
        <div role="alert" className="empty-state flex flex-wrap items-center gap-3 p-5">
          <span className="text-outrange">{t("profile.loadFailed")}</span>
          <Button type="button" variant="outline" onClick={reload} disabled={loading}>{t("profile.retry")}</Button>
        </div>
      ) : (
        <div className="grid min-w-0 gap-6 lg:grid-cols-2">
          <Section id="basics-h" title={t("profile.basicsTitle")}>
            <BasicsForm key={`${p.birth_date}|${p.sex}|${p.height_cm}`} profile={p} onSaved={() => void reload()} />
          </Section>
          <Section id="body-h" title={t("profile.bodyTitle")}><BodyCard profile={p} onChanged={() => void reload()} /></Section>
          <Section id="bmi-h" title={t("profile.bmiTitle")}><BmiCard profile={p} /></Section>
          <Section id="chart-h" title={t("profile.chartTitle")}>
            <BmiChart profileStatus={p.bmi_status} history={data.history} weights={rows.filter((m) => m.kind === "weight")} extra={rows} kind={selected} historyFailed={data.history === null && p.bmi_status === "ok"} />
          </Section>
          <div className="min-w-0 lg:col-span-2">
            <Section id="comp-h" title={t("profile.compTitle")}>
              <CompositionCards body={data.body} rows={rows} bodyFailed={data.body === null && data.measurements === null} selected={selected} onSelect={pickKind} />
            </Section>
          </div>
          <RefillCard profile={p} />
          <div className="min-w-0 lg:col-span-2">
            <Section id="scales-h" title={t("profile.scalesTitle")}><ScalesCard onImported={() => void reload()} /></Section>
          </div>
          <div className="min-w-0 lg:col-span-2">
            <Section id="meas-h" title={t("profile.measurementsTitle")}>
              <MeasurementsList rows={rows} onChanged={() => void reload()} />
            </Section>
          </div>
        </div>
      )}
    </div>
  );
}
