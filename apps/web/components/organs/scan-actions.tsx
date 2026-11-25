"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { useAskBeforeAi } from "@/lib/use-ask-before-ai";

type Props = { busy: "" | "rule" | "ai" | "save"; onRule: () => void; onAi: () => void; onSave: () => void };

/** The three buttons. "Read with AI" asks first (unless the visitor turned that off) because it sends the report to Gemini. */
export function ScanActions({ busy, onRule, onAi, onSave }: Props) {
  const { t } = useI18n();
  const [ask] = useAskBeforeAi();
  const [confirming, setConfirming] = useState(false);
  const off = busy !== "";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="lg" variant="outline" disabled={off} onClick={onRule}>{busy === "rule" ? t("organs.scanReading") : t("organs.scanReadRules")}</Button>
        <Button type="button" size="lg" variant="outline" disabled={off} onClick={() => (ask ? setConfirming(true) : onAi())}>{busy === "ai" ? t("organs.scanReading") : t("organs.scanReadAi")}</Button>
        <Button type="button" size="lg" disabled={off} onClick={onSave}>{busy === "save" ? t("organs.scanSaving") : t("organs.scanSave")}</Button>
      </div>
      {confirming && (
        <div className="space-y-3 rounded-2xl border bg-card/60 p-3">
          <p className="text-sm">{t("organs.scanAiAsk")}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="lg" onClick={() => { setConfirming(false); onAi(); }}>{t("organs.scanAiSend")}</Button>
            <Button type="button" size="lg" variant="outline" onClick={() => setConfirming(false)}>{t("organs.scanAiCancel")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
