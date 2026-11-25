"use client";
import { useRef, useState } from "react";
import { Camera, FileText, ImageIcon, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { postFile, sendJson } from "@/lib/request";
import type { AttachmentOut } from "@/lib/types";
import { ConfirmDelete } from "./confirm-delete";
import { ErrorLine, SectionCard, useAction } from "./kit";

const fileUrl = (id: number) => `/api/attachments/${id}/file`;

export function FilesSection({ recordId, items, reload }: { recordId: number; items: AttachmentOut[]; reload: () => Promise<void> }) {
  const { t, tp, formatNumber } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [progress, setProgress] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const pick = useRef<HTMLInputElement>(null);
  const shoot = useRef<HTMLInputElement>(null);
  const size = (b: number) => (b >= 1_000_000 ? t("timeline.sizeMb", { n: formatNumber(b / 1_000_000, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) }) : t("timeline.sizeKb", { n: formatNumber(Math.max(1, Math.round(b / 1000))) }));

  async function upload(files: FileList | File[]) {
    const list = [...files];
    if (list.length === 0) return;
    const failed: string[] = [];
    setError(null);
    for (const [i, f] of list.entries()) {
      setProgress(t("records.uploading", { i: i + 1, n: list.length }));
      try { await postFile(`records/${recordId}/attachments`, f); } catch (e) { failed.push(`${f.name}: ${(e as Error).message}`); }
    }
    setProgress(null);
    await run(async () => { if (failed.length) throw new Error(failed.join(" ")); });
  }
  const photos = items.filter((f) => f.is_image);
  const others = items.filter((f) => !f.is_image);
  const working = busy || progress !== null;
  return (
    <SectionCard id="files" title={t("records.filesTitle")} count={items.length}>
      <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); void upload(e.dataTransfer.files); }}
        className={`empty-state space-y-3 p-4 text-center transition-colors motion-reduce:transition-none ${over ? "border-primary bg-accent/40" : ""}`}>
        <p className="text-sm text-muted-foreground">{t("records.filesDrop")}</p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button type="button" size="lg" variant="outline" disabled={working} onClick={() => shoot.current?.click()}><Camera aria-hidden />{t("records.takePhoto")}</Button>
          <Button type="button" size="lg" variant="outline" disabled={working} onClick={() => pick.current?.click()}><Paperclip aria-hidden />{t("records.chooseFiles")}</Button>
        </div>
        <input ref={shoot} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => { void upload(e.target.files ?? []); e.target.value = ""; }} />
        <input ref={pick} type="file" multiple accept="application/pdf,image/jpeg,image/png,image/heic,image/heif,.pdf,.jpg,.jpeg,.png,.heic" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => { void upload(e.target.files ?? []); e.target.value = ""; }} />
        {progress && <p role="status" className="text-sm">{progress}</p>}
      </div>
      <ErrorLine message={error} />
      {items.length === 0 && <p className="text-sm text-muted-foreground">{t("records.filesEmpty")}</p>}
      {photos.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((f) => (
            <li key={f.id} className="min-w-0 space-y-1.5">
              <a href={fileUrl(f.id)} target="_blank" rel="noreferrer" title={f.filename} className="block overflow-hidden rounded-2xl border bg-muted/40 outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
                {/* eslint-disable-next-line @next/next/no-img-element -- served by our own API */}
                <img src={fileUrl(f.id)} alt={f.filename} loading="lazy" className="aspect-[4/3] w-full object-cover" />
              </a>
              <div className="flex items-center justify-between gap-1">
                <span className="tnum min-w-0 truncate text-xs text-muted-foreground">{size(f.size_bytes)}</span>
                <ConfirmDelete label={t("records.delete")} question={t("records.confirmFile")} disabled={working} onConfirm={() => run(() => sendJson(`attachments/${f.id}`, "DELETE"))} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <ul className="space-y-2">
          {others.map((f) => (
            <li key={f.id} className="flex min-w-0 items-center gap-2 rounded-2xl border bg-card/60 p-1.5 pl-3">
              {f.mime_type === "application/pdf" ? <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : <ImageIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
              <a href={fileUrl(f.id)} target="_blank" rel="noreferrer" download={f.mime_type === "image/heic" ? f.filename : undefined} className="min-w-0 flex-1 truncate underline-offset-4 hover:underline">{f.filename}</a>
              <span className="tnum shrink-0 text-xs text-muted-foreground">{size(f.size_bytes)}</span>
              <ConfirmDelete label={t("records.delete")} question={t("records.confirmFile")} disabled={working} onConfirm={() => run(() => sendJson(`attachments/${f.id}`, "DELETE"))} />
            </li>
          ))}
        </ul>
      )}
      <span className="sr-only" aria-live="polite">{tp("timeline.files", items.length)}</span>
    </SectionCard>
  );
}
