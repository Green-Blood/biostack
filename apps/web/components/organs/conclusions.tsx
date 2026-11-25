"use client";
import Link from "next/link";
import { ChevronRight, FileText, ImageIcon, PencilLine } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import type { ScanColumn } from "@/lib/types";
import { mentions } from "./table-model";

export const fileUrl = (id: number) => `/api/attachments/${id}/file`;
export const conclusionId = (recordId: number) => `scan-${recordId}`;

/** Verbatim text, line by line. In a report that also covers other organs, the lines about this one get a quiet highlight. */
export function Verbatim({ text, aliases, className = "text-[15px]" }: { text: string; aliases: string[]; className?: string }) {
  const lines = text.split("\n");
  const hit = lines.map((l) => mentions(l, aliases));
  const mixed = lines.some((l, i) => l.trim() && !hit[i]);
  return (
    <div className={`whitespace-pre-wrap break-words leading-relaxed ${className}`}>
      {lines.map((line, i) => mixed && hit[i]
        ? <mark key={i} className="-mx-2 block rounded-[3px] bg-primary/10 px-2 text-foreground shadow-[inset_2px_0_0_var(--primary)]">{line}</mark>
        : <span key={i} className="block">{line || " "}</span>)}
    </div>
  );
}

function Conclusion({ scan, aliases, open, onToggle }: { scan: ScanColumn; aliases: string[]; open: boolean; onToggle: (open: boolean) => void }) {
  const { t, formatDate } = useI18n();
  const details = scan.details?.trim() ?? "", note = scan.doctors_note?.trim() ?? "", body = scan.body_markdown?.trim() ?? "";
  return (
    <li id={conclusionId(scan.record_id)} className="scroll-mt-20">
      <details open={open} onToggle={(e) => onToggle(e.currentTarget.open)} className="group surface overflow-hidden">
        <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <ChevronRight aria-hidden className="size-4 shrink-0 self-center text-muted-foreground transition-transform group-open:rotate-90 motion-reduce:transition-none" />
          <span className="font-semibold tnum">{scan.date ? formatDate(scan.date) : t("organs.noDate")}</span>
          {scan.date_suspect && <span className="rounded-full border border-warn/60 px-2 py-0.5 text-xs text-warn">{t("organs.dateUnconfirmed")}</span>}
          <span className="min-w-[10rem] flex-1 break-words text-muted-foreground">{scan.title}</span>
          {!scan.has_numbers && <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{t("organs.noNumbersBadge")}</span>}
        </summary>
        <div className="space-y-4 border-t px-4 pt-3 pb-4">
          {details || note || body ? (
            <>
              {details && <Verbatim text={details} aliases={aliases} />}
              {note && (
                <div>
                  <div className="eyebrow mb-1">{t("organs.doctorsNote")}</div>
                  <Verbatim text={note} aliases={aliases} />
                </div>
              )}
              {body && <Verbatim text={body} aliases={aliases} />}
            </>
          ) : <p className="text-sm text-muted-foreground">{t("organs.noConclusion")}</p>}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            {scan.attachments.map((f) => (
              <a key={f.id} href={fileUrl(f.id)} target="_blank" rel="noreferrer"
                className="inline-flex min-w-0 max-w-full items-center gap-1.5 underline-offset-4 hover:underline">
                {f.mime_type === "application/pdf" ? <FileText aria-hidden className="size-4 shrink-0 text-muted-foreground" /> : <ImageIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />}
                <span className="truncate">{f.filename}</span>
              </a>
            ))}
            <Link href={`/records/${scan.record_id}`} className="ml-auto inline-flex items-center gap-1.5 text-primary underline-offset-4 hover:underline">
              <PencilLine aria-hidden className="size-4" />{t("organs.editNumbers")}
            </Link>
          </div>
        </div>
      </details>
    </li>
  );
}

/** Every scan's written conclusion, newest first, collapsible; `open` is controlled so a table date can open one. */
export function Conclusions({ scans, aliases, open, setOpen }: { scans: ScanColumn[]; aliases: string[]; open: Set<number>; setOpen: (next: Set<number>) => void }) {
  const { t } = useI18n();
  const newest = [...scans].reverse();
  const all = open.size >= scans.length;
  const toggle = (id: number, isOpen: boolean) => {
    if (open.has(id) === isOpen) return;
    const next = new Set(open);
    if (isOpen) next.add(id); else next.delete(id);
    setOpen(next);
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="max-w-prose text-sm text-muted-foreground">{t("organs.conclusionsHint")}</p>
        {scans.length > 1 && (
          <button type="button" onClick={() => setOpen(all ? new Set() : new Set(scans.map((s) => s.record_id)))}
            className="text-sm text-primary underline-offset-4 hover:underline">
            {t(all ? "organs.collapseAll" : "organs.expandAll")}
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {newest.map((s) => <Conclusion key={s.record_id} scan={s} aliases={aliases} open={open.has(s.record_id)} onToggle={(o) => toggle(s.record_id, o)} />)}
      </ul>
    </div>
  );
}
