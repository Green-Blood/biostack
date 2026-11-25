"use client";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getJson } from "@/lib/request";
import { useI18n } from "@/lib/i18n/client";
import { AiOffNote, TestLists, type Insight, type TestIdea } from "./insight-parts";

type Guide = Insight & {
  markers?: { key: string; meaning: string; typical_range?: string; if_off: string; action: string }[];
  tests_skip?: TestIdea[];
};

/** On-demand AI guide for one body-system panel: what each marker is, why it runs high or low, what to do, which tests to add or skip. */
export function PanelInsight({ system, names, outKeys }: { system: string; names: Record<string, string>; outKeys: string[] }) {
  const { t } = useI18n();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load(refresh: boolean) {
    setBusy(true); setError("");
    try { setGuide(await getJson<Guide>(`insights/system/${encodeURIComponent(system)}${refresh ? "?refresh=true" : ""}`)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  // Out-of-range markers first: they are why the panel was opened.
  const markers = [...(guide?.markers ?? [])].filter((m) => names[m.key]).sort((a, b) => Number(outKeys.includes(b.key)) - Number(outKeys.includes(a.key)));
  return (
    <div className="mt-2 space-y-3">
      {!guide && <Button size="sm" variant="outline" disabled={busy} onClick={() => load(false)}><Sparkles className="size-4" aria-hidden />{busy ? t("biomarkers.insightBusy") : t("biomarkers.insightAsk")}</Button>}
      <div aria-live="polite" className="space-y-2">
        {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
        {guide && !guide.ai_enabled && <AiOffNote />}
      </div>
      {guide?.ai_enabled && (
        <div className="surface space-y-4 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-semibold">{t("biomarkers.insightTitle")}</h3>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => load(true)}>{busy ? t("biomarkers.insightBusy") : t("biomarkers.insightRefresh")}</Button>
          </div>
          <ul className="space-y-3">
            {markers.map((m) => (
              <li key={m.key} className="text-sm">
                <p className={`font-medium ${outKeys.includes(m.key) ? "text-outrange" : ""}`}>{names[m.key]}</p>
                <p><span className="text-muted-foreground">{t("biomarkers.insightMeaning")}: </span>{m.meaning}</p>
                {m.typical_range && <p><span className="text-muted-foreground">{t("biomarkers.insightRange")}: </span>{m.typical_range}</p>}
                <p><span className="text-muted-foreground">{t("biomarkers.insightIfOff")}: </span>{m.if_off}</p>
                <p><span className="text-muted-foreground">{t("biomarkers.insightAction")}: </span>{m.action}</p>
              </li>
            ))}
          </ul>
          <TestLists worth={guide.tests_worth_it} skip={guide.tests_skip} />
          <p className="text-xs text-muted-foreground">{t("biomarkers.insightDisclaimer")}</p>
        </div>
      )}
    </div>
  );
}
