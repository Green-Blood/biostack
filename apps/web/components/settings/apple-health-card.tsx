"use client";
import { useRef, useState } from "react";
import { FileArchive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/client";

type AppleImportSummary = { days_written: number; fields_written: number; records_scanned: number; sleep_nights: number };

export function AppleHealthCard() {
  const { t } = useI18n();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/imports/apple-health", { method: "POST", body: form });
      if (!res.ok) {
        setMessage({ text: await errorMessage(res, t("settings.appleFailed")), ok: false });
        return;
      }
      const done = (await res.json()) as AppleImportSummary;
      setMessage({
        text: t("settings.appleDone", {
          days: done.days_written,
          fields: done.fields_written,
          nights: done.sleep_nights,
          records: done.records_scanned,
        }),
        ok: true,
      });
    } catch {
      setMessage({ text: t("settings.exportUnreachable"), ok: false });
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm text-muted-foreground">{t("settings.appleText")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="lg" onClick={() => fileInput.current?.click()} disabled={busy}>
          <FileArchive aria-hidden /> {busy ? t("settings.appleImporting") : t("settings.appleButton")}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          tabIndex={-1}
          aria-label={t("settings.appleTitle")}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }}
        />
        {message && (
          <p aria-live="polite" role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-ok" : "text-outrange"}`}>
            {message.text}
          </p>
        )}
      </div>
    </div>
  );
}
