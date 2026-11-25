"use client";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { errorMessage } from "@/lib/api-error";
import { todayIso } from "@/lib/format-date";

export function DataExport() {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [dicom, setDicom] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  async function download() {
    setBusy(true); setMessage(null);
    try {
      const res = await fetch(`/api/settings/export/archive${dicom ? "?include_dicom=true" : ""}`, { cache: "no-store" });
      if (!res.ok) { setMessage({ text: await errorMessage(res, t("settings.exportFailed")), ok: false }); return; }
      const link = document.createElement("a");
      link.href = URL.createObjectURL(await res.blob());
      link.download = `biostack-export-${todayIso()}.zip`;
      link.click();
      URL.revokeObjectURL(link.href);
      setMessage({ text: t("settings.exportDone"), ok: true });
    } catch {
      setMessage({ text: t("settings.exportUnreachable"), ok: false });
    } finally {
      setBusy(false);
    }
  }

  async function restore(file: File) {
    setBusy(true); setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/settings/import/archive", { method: "POST", body: form });
      if (!res.ok) { setMessage({ text: await errorMessage(res, t("settings.importFailed")), ok: false }); return; }
      const done = (await res.json()) as { rows: number; files: number };
      setMessage({ text: t("settings.importDone").replace("{rows}", String(done.rows)).replace("{files}", String(done.files)), ok: true });
    } catch {
      setMessage({ text: t("settings.exportUnreachable"), ok: false });
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm text-muted-foreground">{t("settings.exportText")}</p>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dicom} onChange={(e) => setDicom(e.target.checked)} /> {t("settings.exportDicom")}</label>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={download} disabled={busy}><Download aria-hidden /> {busy ? t("settings.exporting") : t("settings.exportButton")}</Button>
        <Button size="lg" variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}><Upload aria-hidden /> {t("settings.importButton")}</Button>
        <input ref={fileInput} type="file" accept=".zip,application/zip" className="sr-only" tabIndex={-1} aria-label={t("settings.importTitle")}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void restore(f); }} />
        <p aria-live="polite" role={message?.ok === false ? "alert" : "status"} className={`text-sm ${message?.ok === false ? "text-outrange" : "text-muted-foreground"}`}>{message?.text}</p>
      </div>
    </div>
  );
}
