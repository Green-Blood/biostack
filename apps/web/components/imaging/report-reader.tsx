"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api-error";
import type { ReportDraft } from "@/lib/types";
import { useAskBeforeAi } from "@/lib/use-ask-before-ai";
import { useI18n } from "@/lib/i18n/client";

type Props = { studyId: number; onDraft: (draft: ReportDraft) => void };

/** Optional: reads a report file with the AI and hands the text back for editing. Nothing is saved here. */
export function ReportReader({ studyId, onDraft }: Props) {
  const { t } = useI18n();
  const [ask] = useAskBeforeAi();
  const [pending, setPending] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function send(file: File) {
    setPending(null); setError(null); setDone(false); setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/imaging/${studyId}/report`, { method: "POST", body });
      if (!res.ok) { setError(await errorMessage(res, t("imaging.reportFailed"))); return; }
      onDraft((await res.json()) as ReportDraft);
      setDone(true);
    } catch {
      setError(t("imaging.apiUnreachable"));
    } finally {
      setBusy(false);
    }
  }

  function choose(file: File | undefined) {
    if (!file) return;
    if (ask) { setPending(file); setError(null); setDone(false); } else void send(file);
  }

  return (
    <div className="space-y-3 surface p-4">
      <div>
        <p className="font-medium">{t("imaging.fillFromReport")}</p>
        <p className="text-sm text-muted-foreground">{t("imaging.fillFromReportHint")}</p>
      </div>
      <input type="file" accept="application/pdf,image/png,image/jpeg" aria-label={t("imaging.chooseReport")} disabled={busy}
        onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }}
        className="block w-full text-sm file:mr-3 file:rounded-xl file:border file:bg-background file:px-3 file:py-1.5 file:text-sm" />
      <div aria-live="polite" className="space-y-2">
        {busy && <p role="status" className="text-sm">{t("imaging.readingReport")}</p>}
        {done && <p role="status" className="text-sm">{t("imaging.draftAdded")}</p>}
        {pending && (
          <div className="space-y-3">
            <p className="text-sm">{t("imaging.sendReportBefore")} <strong className="font-medium">{pending.name}</strong> {t("imaging.sendReportAfter")}</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => send(pending)}>{t("imaging.sendToAi")}</Button>
              <Button size="sm" variant="outline" onClick={() => setPending(null)}>{t("imaging.cancel")}</Button>
            </div>
          </div>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
    </div>
  );
}
