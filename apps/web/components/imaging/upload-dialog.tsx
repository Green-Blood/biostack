"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api-error";
import type { UploadedStudy } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";

type Props = { open: boolean; onClose: () => void; onUploaded: (study: UploadedStudy) => void; onOpenExisting: (id: number) => void };

export function UploadDialog({ open, onClose, onUploaded, onOpenExisting }: Props) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existingId, setExistingId] = useState<number | null>(null);

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) { setError(t("imaging.chooseZipFirst")); return; }
    setBusy(true); setError(null); setExistingId(null);
    try {
      const body = new FormData(e.currentTarget);
      body.set("file", file);
      for (const [key, value] of [...body.entries()]) if (value === "") body.delete(key);
      const res = await fetch("/api/imaging/upload", { method: "POST", body });
      if (res.ok) { setFile(null); onUploaded((await res.json()) as UploadedStudy); return; }
      if (res.status === 409) setExistingId((await res.clone().json())?.detail?.study_id ?? null);
      setError(await errorMessage(res, t("imaging.uploadFailed")));
    } catch {
      setError(t("imaging.apiUnreachable"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="upload-title"
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border bg-card p-0 text-card-foreground backdrop:bg-black/50">
      <form onSubmit={submit} className="space-y-5 p-6">
        <h2 id="upload-title" className="font-semibold">{t("imaging.uploadStudy")}</h2>
        <p className="text-sm text-muted-foreground">{t("imaging.uploadIntro")}</p>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.zipArchive")}</span>
          <input type="file" name="file" accept=".zip,application/zip" disabled={busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-xl file:border file:bg-background file:px-3 file:py-1.5 file:text-sm" /></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.studyDateOptional")}</span><Input type="date" name="study_date" className="tnum" /></label>
          <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.typeOptional")}</span><Input name="study_type" placeholder={t("imaging.typePlaceholder")} autoComplete="off" /></label>
        </div>
        <label className="block space-y-1.5 text-sm"><span className="font-medium">{t("imaging.bodyPartOptional")}</span><Input name="body_part" autoComplete="off" /></label>
        <div aria-live="polite">
          {busy && (
            <div role="status" className="space-y-2">
              <p className="text-sm">{t("imaging.readingSlices")}</p>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full w-1/3 rounded-full bg-[var(--data)] motion-safe:animate-pulse" /></div>
            </div>
          )}
        </div>
        {error && (
          <div role="alert" className="space-y-2 text-sm text-outrange">
            <p>{error}</p>
            {existingId !== null && <Button type="button" size="sm" variant="outline" onClick={() => onOpenExisting(existingId)}>{t("imaging.openSaved")}</Button>}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="lg" disabled={busy}>{busy ? t("imaging.uploading") : t("imaging.uploadSubmit")}</Button>
          <Button type="button" size="lg" variant="outline" onClick={onClose} disabled={busy}>{t("imaging.cancel")}</Button>
        </div>
      </form>
    </dialog>
  );
}
