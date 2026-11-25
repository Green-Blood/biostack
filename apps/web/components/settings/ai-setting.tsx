"use client";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import { useAskBeforeAi } from "@/lib/use-ask-before-ai";
import type { UserSettings } from "@/lib/types";
import { useStatus } from "./use-status";

type AiStatus = { provider: string; model: string | null; configured: boolean; base_url: string | null };
type AiTestResult = { ok: boolean; provider?: string; model?: string; error?: string };

export function AiSetting({ aiBriefing }: { aiBriefing: boolean }) {
  const { t } = useI18n();
  const [ask, setAsk] = useAskBeforeAi();
  const [briefing, setBriefing] = useState(aiBriefing);
  const [status, show] = useStatus();
  const [aiInfo, setAiInfo] = useState<AiStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    getJson<AiStatus>("settings/ai-status")
      .then((res) => { if (alive) setAiInfo(res); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  async function testConnection() {
    setTesting(true);
    setTestMsg(null);
    try {
      const res = await sendJson<AiTestResult>("settings/ai-test", "POST", {});
      if (res.ok) {
        setTestMsg({ text: t("settings.aiTestOk", { provider: res.provider ?? "ai", model: res.model ?? "" }), ok: true });
      } else {
        setTestMsg({ text: t("settings.aiTestFailed", { error: res.error ?? "unknown error" }), ok: false });
      }
    } catch (error) {
      setTestMsg({ text: t("settings.aiTestFailed", { error: (error as Error).message }), ok: false });
    } finally {
      setTesting(false);
    }
  }

  async function changeBriefing(next: boolean) {
    show(null);
    try {
      const saved = await sendJson<UserSettings>("settings", "PATCH", { ai_briefing: next });
      setBriefing(saved.ai_briefing);
      show({ text: saved.ai_briefing ? t("settings.aiBriefingOn") : t("settings.aiBriefingTurnedOff"), ok: true });
    } catch (error) {
      show({ text: (error as Error).message, ok: false });
    }
  }

  const providerLabel = aiInfo?.provider === "openai_compat"
    ? t("settings.aiProviderOpenAi")
    : aiInfo?.provider === "fake"
      ? t("settings.aiProviderFake")
      : t("settings.aiProviderGemini");

  return (
    <div className="space-y-5">
      {aiInfo && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card/60 p-3.5 text-sm">
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">{t("settings.aiProviderLabel")}:</span>
              <span className="font-medium">{providerLabel}</span>
              <Badge variant={aiInfo.configured ? "secondary" : "outline"}>
                {aiInfo.configured && aiInfo.model ? `${t("settings.aiModelLabel")}: ${aiInfo.model}` : t("settings.aiNotConfigured")}
              </Badge>
            </div>
            {aiInfo.base_url && <p className="text-xs text-muted-foreground">{aiInfo.base_url}</p>}
          </div>
          <Button type="button" size="sm" variant="outline" onClick={testConnection} disabled={testing}>
            {testing ? t("settings.aiTesting") : t("settings.aiTestButton")}
          </Button>
          {testMsg && (
            <p aria-live="polite" role={testMsg.ok ? "status" : "alert"} className={`w-full text-sm ${testMsg.ok ? "text-ok" : "text-outrange"}`}>
              {testMsg.text}
            </p>
          )}
        </div>
      )}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold">{t("settings.aiPdfTitle")}</h3>
        <p className="max-w-prose text-sm text-muted-foreground">{t("settings.aiPdfText")}</p>
        <label className="flex items-center gap-2.5 text-sm">
          <input type="checkbox" checked={ask} onChange={(e) => setAsk(e.target.checked)} className="size-4 accent-[var(--data)]" />
          {t("settings.aiAsk")}
        </label>
      </div>
      <div className="space-y-3 border-t pt-5">
        <h3 className="text-lg font-semibold">{t("settings.aiBriefingTitle")}</h3>
        <p className="max-w-prose text-sm text-muted-foreground">{t("settings.aiBriefingOff")}</p>
        <label className="flex items-start gap-2.5 text-sm">
          <input type="checkbox" checked={briefing} onChange={(e) => changeBriefing(e.target.checked)} aria-describedby="ai-briefing-sent" className="mt-0.5 size-4 accent-[var(--data)]" />
          <span className="font-medium">{t("settings.aiBriefingLabel")}</span>
        </label>
        <p id="ai-briefing-sent" className="max-w-prose text-sm text-muted-foreground">
          {t("settings.aiBriefingSent")}
        </p>
        {status && <p aria-live="polite" role={status.ok ? "status" : "alert"} className={`text-sm ${status.ok ? "text-muted-foreground" : "text-outrange"}`}>{status.text}</p>}
      </div>
    </div>
  );
}
