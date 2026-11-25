"use client";
import Link from "next/link";
import { ChevronDown, FileText, ImageIcon, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { ReviewTable } from "./review-table";
import { emptyRow, isBlank } from "@/lib/lab-rows";
import { isLabItem, type InboxItem, type Kind, type RecordRef, type Status } from "./inbox-model";

const KIND_LABEL: Record<Kind, Key> = { lab: "inbox.kindLab", imaging_report: "inbox.kindImaging", other: "inbox.kindOther" };
const STATUS_LABEL: Record<Status, Key> = {
  queued: "inbox.statusQueued", analysing: "inbox.statusAnalysing", review: "inbox.statusReview", ready: "inbox.statusReady",
  needs_ai: "inbox.statusNeedsAi", ai_reading: "inbox.statusAiReading", already_saved: "inbox.statusAlready", error: "inbox.statusError",
  saved: "inbox.statusSaved", not_saved: "inbox.statusNotSaved",
};
const STATUS_TONE: Record<Status, string> = {
  queued: "text-muted-foreground", analysing: "text-muted-foreground", ai_reading: "text-muted-foreground", review: "text-warn", ready: "text-ok",
  needs_ai: "text-warn", already_saved: "text-muted-foreground", error: "text-outrange", saved: "text-ok", not_saved: "text-outrange",
};
const SELECT = "h-9 w-full rounded-xl border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

type Props = {
  item: InboxItem; records: RecordRef[]; askBeforeAi: boolean; markerListId: string;
  onChange: (patch: Partial<InboxItem>) => void; onRemove: () => void; onSendAi: () => void;
};

export function InboxItemCard({ item, records, askBeforeAi, markerListId, onChange, onRemove, onSendAi }: Props) {
  const { t, tp, formatDate } = useI18n();
  const busy = item.status === "queued" || item.status === "analysing" || item.status === "ai_reading";
  const done = item.status === "saved";
  const lab = isLabItem(item);
  const showFields = !busy && item.status !== "needs_ai";
  const editableRows = lab && item.status !== "already_saved" && !done && !busy && item.status !== "needs_ai";
  const label = (r: RecordRef) => ({ title: r.title, date: r.date ? ` · ${formatDate(r.date)}` : "" });
  const options = item.suggested && !records.some((r) => r.id === item.suggested!.id) ? [item.suggested, ...records] : records;
  return (
    <li className="space-y-3 rounded-2xl border border-border bg-card p-3 shadow-card sm:p-4" aria-busy={busy}>
      <div className="flex items-start gap-3">
        <input type="checkbox" checked={item.include} disabled={busy || done} onChange={(e) => onChange({ include: e.target.checked })}
          aria-label={t("inbox.include", { name: item.name })} className="mt-1 size-4 shrink-0 accent-[var(--data)]" />
        <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted text-muted-foreground">
          {item.thumb
            ? (
              // eslint-disable-next-line @next/next/no-img-element -- a local blob preview, not an optimisable asset
              <img src={item.thumb} alt={t("inbox.thumbAlt", { name: item.name })} className="size-full object-cover" />
            )
            : item.file?.type.startsWith("image/") || /\.heic$/i.test(item.name) ? <ImageIcon className="size-5" aria-hidden /> : <FileText className="size-5" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="break-words font-medium">{item.file ? item.name : t("inbox.manualTitle")}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="rounded-full border border-border px-2 py-0.5 text-muted-foreground">{item.file ? t(KIND_LABEL[item.kind]) : t("inbox.kindManual")}</span>
            <span className={`font-medium ${STATUS_TONE[item.status]}`}>
              {busy && <span className="mr-1.5 inline-block size-2 rounded-full bg-current motion-safe:animate-pulse" aria-hidden />}
              {t(STATUS_LABEL[item.status])}
            </span>
            {item.readBy && !done && <span className="text-muted-foreground">{item.readBy === "local" ? t("inbox.readLocal") : t("inbox.readAi")}</span>}
          </div>
        </div>
        {!busy && (
          <Button type="button" variant="ghost" size="icon-sm" onClick={onRemove} aria-label={t("inbox.remove", { name: item.file ? item.name : t("inbox.manualTitle") })}><X aria-hidden /></Button>
        )}
      </div>

      {item.message && !done && <p role="alert" className="text-sm text-outrange">{item.message}</p>}

      {item.status === "needs_ai" && (
        <div className="space-y-3 rounded-xl border border-border bg-background/50 p-3">
          <p className="max-w-prose text-sm">{t("inbox.needsAiText")}</p>
          {item.confirmAi ? (
            <div className="space-y-3">
              <p className="max-w-prose text-sm">{t("inbox.sendConfirm", { name: item.name })}</p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={onSendAi}>{t("inbox.sendToAi")}</Button>
                <Button type="button" variant="outline" onClick={() => onChange({ confirmAi: false })}>{t("inbox.cancel")}</Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => (askBeforeAi ? onChange({ confirmAi: true }) : onSendAi())}>{t("inbox.sendToAi")}</Button>
              <Button type="button" variant="outline" onClick={() => onChange({ kind: "lab", status: "review", open: true, rows: item.rows.length ? item.rows : [emptyRow()] })}>{t("inbox.enterByHand")}</Button>
              <Button type="button" variant="ghost" onClick={() => onChange({ kind: "other", status: "ready" })}>{t("inbox.attachOnly")}</Button>
            </div>
          )}
        </div>
      )}

      {item.status === "already_saved" && <p className="max-w-prose text-sm text-muted-foreground">{t("inbox.alreadySavedText")}</p>}

      {showFields && !done && (
        <div className="grid gap-3 sm:grid-cols-2">
          {!item.file ? null : item.status !== "already_saved" && !lab && (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{t("inbox.kindLabel")}</span>
              <select className={SELECT} value={item.kind} onChange={(e) => onChange({ kind: e.target.value as Kind })}>
                <option value="imaging_report">{t("inbox.kindImaging")}</option>
                <option value="other">{t("inbox.kindOther")}</option>
              </select>
            </label>
          )}
          {item.file && (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{t("inbox.record")}</span>
              <select className={SELECT} value={item.record} onChange={(e) => onChange({ record: e.target.value })}>
                <option value="new">{t("inbox.recordNew")}</option>
                {options.map((r) => (
                  <option key={r.id} value={String(r.id)}>
                    {t(item.suggested?.id === r.id ? "inbox.recordSuggested" : "inbox.recordOption", label(r))}
                  </option>
                ))}
              </select>
            </label>
          )}
          {item.status !== "already_saved" && (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{lab ? t("inbox.testDate") : t("inbox.date")}</span>
              <Input type="date" value={item.date} onChange={(e) => onChange({ date: e.target.value })} className="tnum" />
            </label>
          )}
          {lab && item.status !== "already_saved" && (
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">{t("inbox.laboratory")}</span>
              <Input value={item.lab} onChange={(e) => onChange({ lab: e.target.value })} autoComplete="off" />
            </label>
          )}
          {item.file && item.record === "new" && item.status !== "already_saved" && (
            <label className="block space-y-1.5 text-sm sm:col-span-2">
              <span className="font-medium">{t("inbox.recordTitle")}</span>
              <Input value={item.title} onChange={(e) => onChange({ title: e.target.value })} autoComplete="off" />
              <span className="block text-xs text-muted-foreground">{t("inbox.recordTitleHint")}</span>
            </label>
          )}
        </div>
      )}

      {editableRows && (
        <div className="space-y-3">
          <button type="button" aria-expanded={item.open} onClick={() => onChange({ open: !item.open })}
            className="inline-flex items-center gap-1.5 rounded-xl text-sm font-medium underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
            <ChevronDown className={`size-4 motion-safe:transition-transform ${item.open ? "rotate-180" : ""}`} aria-hidden />
            {item.open ? t("inbox.hideResults") : tp("inbox.reviewResults", item.rows.filter((r) => !isBlank(r)).length)}
          </button>
          {item.open && <ReviewTable rows={item.rows} onChange={(rows) => onChange({ rows })} markerListId={markerListId} />}
        </div>
      )}

      {done && (
        <p role="status" className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {item.recordId !== null && <Link href={`/timeline?record=${item.recordId}`} className="underline underline-offset-4">{t("inbox.openRecord")}</Link>}
          {lab && <Link href="/biomarkers" className="underline underline-offset-4">{t("inbox.openBiomarkers")}</Link>}
        </p>
      )}
    </li>
  );
}
