"use client";
import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { sendJson } from "@/lib/request";
import type { Briefing } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";

export function BriefingCard({ initial }: { initial: Briefing }) {
  const { t } = useI18n();
  const [briefing, setBriefing] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function tryAgain() {
    setBusy(true); setError("");
    try {
      setBriefing(await sendJson<Briefing>("analytics/briefing/refresh", "POST"));
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  const ai = briefing.source === "ai";
  return (
    <section aria-labelledby="brief-h" className="surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h2 id="brief-h">{t("overview.briefingTitle")}</h2>
        <span className="text-sm text-muted-foreground">{ai ? t("overview.briefingAi") : briefing.label || t("overview.briefingFallback")}</span>
      </div>
      <ul className="mt-3 list-disc space-y-2 pl-5">{briefing.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
      <div aria-live="polite" className="mt-4 space-y-2 text-sm text-muted-foreground">
        {!briefing.ai_enabled && <p>{t("overview.aiOff")} <Link href="/settings#ai" className="underline underline-offset-4">{t("overview.aiOffLink")}</Link>.</p>}
        {briefing.can_retry && (
          <div className="flex flex-wrap items-center gap-3">
            <p>{t("overview.aiFailed")}</p>
            <Button size="sm" variant="outline" disabled={busy} onClick={tryAgain}>{busy ? t("overview.trying") : t("overview.tryAgain")}</Button>
          </div>
        )}
        {error && <p role="alert" className="text-outrange">{error}</p>}
      </div>
    </section>
  );
}
