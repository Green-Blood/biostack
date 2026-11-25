"use client";
import { useRef, useState } from "react";
import { FileUp, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";

type Props = { onFiles: (files: File[]) => void };

type Entry = { isFile: boolean; isDirectory: boolean; file?: (cb: (f: File) => void, err?: () => void) => void; createReader?: () => { readEntries: (cb: (e: Entry[]) => void, err?: () => void) => void } };

async function readEntry(entry: Entry): Promise<File[]> {
  if (entry.isFile && entry.file) return [await new Promise<File>((resolve, reject) => entry.file!(resolve, reject))];
  if (!entry.isDirectory || !entry.createReader) return [];
  const reader = entry.createReader();
  const found: File[] = [];
  for (;;) { // readEntries returns in batches until it returns an empty one
    const batch = await new Promise<Entry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (batch.length === 0) break;
    for (const child of batch) found.push(...(await readEntry(child)));
  }
  return found;
}

/** Files from a drop, including every file inside dropped folders. */
async function filesFromDrop(data: DataTransfer): Promise<File[]> {
  const entries = [...data.items].map((i) => (i as DataTransferItem & { webkitGetAsEntry?: () => Entry | null }).webkitGetAsEntry?.() ?? null);
  if (entries.some((e) => e === null)) return [...data.files]; // browser without folder support
  const nested = await Promise.all(entries.map((e) => readEntry(e as Entry).catch(() => [] as File[])));
  return nested.flat();
}

const ACCEPT = "application/pdf,image/jpeg,image/png,image/heic,.pdf,.jpg,.jpeg,.png,.heic";

export function InboxDropZone({ onFiles }: Props) {
  const { t } = useI18n();
  const [dragging, setDragging] = useState(false);
  const folderRef = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-3">
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void filesFromDrop(e.dataTransfer).then(onFiles); }}
        className={`flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-5 py-12 text-center shadow-card transition-colors focus-within:ring-3 focus-within:ring-ring/50 sm:py-16 ${dragging ? "border-[var(--data)] bg-accent/60" : "border-border bg-card hover:bg-accent/40"}`}
      >
        <FileUp className="size-9 text-[var(--data)]" aria-hidden />
        <span className="font-heading text-xl">{t("inbox.dropHeading")}</span>
        <span className="max-w-prose text-sm text-muted-foreground">{t("inbox.dropHint")}</span>
        <span className="rounded-xl border border-border px-3 py-1.5 text-sm font-medium">{t("inbox.chooseFiles")}</span>
        <input type="file" multiple accept={ACCEPT} className="sr-only" aria-label={t("inbox.dropAria")}
          onChange={(e) => { onFiles([...(e.target.files ?? [])]); e.target.value = ""; }} />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => folderRef.current?.click()}><FolderOpen aria-hidden /> {t("inbox.chooseFolder")}</Button>
        <input ref={folderRef} type="file" className="sr-only" tabIndex={-1} aria-hidden
          {...({ webkitdirectory: "", directory: "", multiple: true } as Record<string, unknown>)}
          onChange={(e) => { onFiles([...(e.target.files ?? [])]); e.target.value = ""; }} />
      </div>
    </div>
  );
}
