"use client";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getJson } from "@/lib/request";
import { useI18n } from "@/lib/i18n/client";
import { AiOffNote, TestLists, type Insight } from "./insight-parts";

type Guide = Insight & { meaning?: string; typical_range?: string; if_high?: string; if_low?: string; action?: string };

/** AI explanation for a marker that has no hand-written text: what it is, why high or low, what to do, which tests to add. */
export function AiMarkerGuide({ markerKey }: { markerKey: string }) {
  const { t } = useI18n();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load(refresh: boolean) {
    setBusy(true); setError("");
    try { setGuide(await getJson<Guide>(`insights/marker/${encodeURIComponent(markerKey)}${refresh ? "?refresh=true" : ""}`)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const row = (label: string, text?: string) => text && <p><strong>{label}: </strong>{text}</p>;
  return (
    <div className="space-y-3">
      {!guide?.ai_enabled && <Button size="sm" variant="outline" disabled={busy} onClick={() => load(false)}><Sparkles className="size-4" aria-hidden />{busy ? t("biomarkers.insightBusy") : t("biomarkers.insightAskMarker")}</Button>}
      <div aria-live="polite" className="space-y-3">
        {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
        {guide && !guide.ai_enabled && <AiOffNote />}
        {guide?.ai_enabled && <>
          {guide.meaning && <p>{guide.meaning}</p>}
          {row(t("biomarkers.insightRange"), guide.typical_range)}
          {row(t("biomarkers.insightIfHigh"), guide.if_high)}
          {row(t("biomarkers.insightIfLow"), guide.if_low)}
          {row(t("biomarkers.insightAction"), guide.action)}
          <TestLists worth={guide.tests_worth_it} />
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => load(true)}>{busy ? t("biomarkers.insightBusy") : t("biomarkers.insightRefresh")}</Button>
        </>}
      </div>
    </div>
  );
}
