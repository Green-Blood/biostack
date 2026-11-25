"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { AiOffNote, TestLists, type Insight } from "@/components/biomarkers/insight-parts";
import { getJson } from "@/lib/request";
import { useI18n } from "@/lib/i18n/client";

type Overview = Insight & {
  health_pct: number | null; ok: number; total: number;
  summary?: string; actions?: { title: string; detail: string }[];
};

/** Health score from the stored results (plain arithmetic) plus an AI-written summary of how to raise it, re-asked at most daily. */
export function AiHealthCard() {
  const { t } = useI18n();
  const [data, setData] = useState<Overview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  async function load(refresh: boolean) {
    setBusy(true); setError("");
    try { setData(await getJson<Overview>(`insights/overview${refresh ? "?refresh=true" : ""}`)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    let alive = true;
    getJson<Overview>("insights/overview")
      .then((res) => { if (alive) setData(res); })
      .catch((e) => { if (alive) setError((e as Error).message); })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, []);

  if (!data && !busy && !error) return null;
  return (
    <section aria-labelledby="health-h" className="surface space-y-3 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h2 id="health-h">{t("biomarkers.healthTitle")}</h2>
        {data?.ai_enabled && <Button size="sm" variant="ghost" disabled={busy} onClick={() => load(true)}>{busy ? t("biomarkers.insightBusy") : t("biomarkers.insightRefresh")}</Button>}
      </div>
      {data?.health_pct != null && (
        <p className="flex items-baseline gap-3"><span className="text-4xl font-semibold tnum">{data.health_pct}%</span><span className="text-muted-foreground">{t("biomarkers.healthPct", { ok: data.ok, total: data.total })}</span></p>
      )}
      <div aria-live="polite" className="space-y-3">
        {busy && <p className="text-sm text-muted-foreground">{t("biomarkers.insightBusy")}</p>}
        {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
        {data && !data.ai_enabled && <AiOffNote />}
        {data?.summary && <p>{data.summary}</p>}
        {data?.actions && data.actions.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold">{t("biomarkers.healthHow")}</h3>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">
              {data.actions.map((a) => <li key={a.title}><span className="font-medium">{a.title}.</span> {a.detail}</li>)}
            </ol>
          </div>
        )}
        {data?.summary && <TestLists worth={data.tests_worth_it} />}
        {data?.summary && <p className="text-xs text-muted-foreground">{t("biomarkers.insightDisclaimer")}</p>}
      </div>
    </section>
  );
}
