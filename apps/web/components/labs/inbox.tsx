"use client";
import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/client";
import { emptyRow, isBlank, rowFromDraft, toPayload } from "@/lib/lab-rows";
import type { UploadDraft } from "@/lib/types";
import { useAskBeforeAi } from "@/lib/use-ask-before-ai";
import { InboxDropZone } from "./inbox-drop-zone";
import { InboxItemCard } from "./inbox-item";
import { isAccepted, isLabItem, rowProblems, savable, type Analysis, type InboxItem, type ItemResult, type RecordRef } from "./inbox-model";

const CONCURRENCY = 3;
const NEAR_DAYS = 14;
let counter = 0;

const blank = (over: Partial<InboxItem>): InboxItem => ({
  id: `item-${++counter}`, file: null, name: "", status: "queued", kind: "other", hash: "", readBy: null, rows: [], date: "", lab: "",
  record: "new", suggested: null, title: "", include: true, open: false, confirmAi: false, message: null, recordId: null, thumb: null, ...over,
});

/** The record dated closest to `date` within two weeks, like the server's suggestion for text PDFs. */
function nearestRecord(records: RecordRef[], date: string | null): RecordRef | null {
  if (!date) return null;
  const at = Date.parse(date);
  const near = records.filter((r) => r.date && Math.abs(Date.parse(r.date) - at) <= NEAR_DAYS * 864e5);
  near.sort((a, b) => Math.abs(Date.parse(a.date!) - at) - Math.abs(Date.parse(b.date!) - at));
  return near[0] ?? null;
}

type DraftWithMethod = UploadDraft & { method?: "text" | "ai" };

export function Inbox({ markerNames, records }: { markerNames: string[]; records: RecordRef[] }) {
  const { t, tp } = useI18n();
  const listId = useId();
  const [ask, setAsk] = useAskBeforeAi();
  const [items, setItems] = useState<InboxItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const thumbs = useRef<string[]>([]);

  useEffect(() => () => thumbs.current.forEach((u) => URL.revokeObjectURL(u)), []);

  const patch = (id: string, change: Partial<InboxItem>) => setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...change } : i)));

  function addFiles(files: File[]) {
    const ok = files.filter(isAccepted);
    setSkipped(files.filter((f) => !isAccepted(f)).map((f) => f.name));
    setNotice(null);
    setItems((prev) => [...prev, ...ok.map((file) => {
      const thumb = /^image\/(jpeg|png)$/.test(file.type) ? URL.createObjectURL(file) : null;
      if (thumb) thumbs.current.push(thumb);
      return blank({ file, name: file.name, thumb });
    })]);
  }

  function addManual() {
    setItems((prev) => [...prev, blank({ kind: "lab", status: "review", rows: [emptyRow()], open: true })]);
  }

  async function analyse(item: InboxItem) {
    try {
      const body = new FormData();
      body.append("file", item.file!);
      const res = await fetch("/api/inbox/analyze", { method: "POST", body });
      if (!res.ok) { patch(item.id, { status: "error", message: await errorMessage(res, t("inbox.analyseFailed")), include: false }); return; }
      const found = (await res.json()) as Analysis;
      setItems((prev) => {
        if (prev.some((o) => o.id !== item.id && o.hash === found.file_hash)) {
          return prev.map((i) => (i.id === item.id ? { ...i, status: "error", message: t("inbox.duplicateInList"), include: false } : i));
        }
        const draft = found.draft as DraftWithMethod | null;
        const suggested = found.suggested_record ?? nearestRecord(records, draft?.test_date ?? null);
        const common = { hash: found.file_hash, kind: found.kind, suggested, record: suggested ? String(suggested.id) : "new", message: null };
        const change: Partial<InboxItem> = found.already_saved
          ? { ...common, status: "already_saved", kind: "lab" }
          : draft
            ? { ...common, status: "review", rows: draft.rows.map(rowFromDraft), date: draft.test_date ?? "", lab: draft.lab_name, readBy: draft.method === "ai" ? "ai" : "local" }
            : { ...common, status: found.needs_ai ? "needs_ai" : "ready" };
        return prev.map((i) => (i.id === item.id ? { ...i, ...change } : i));
      });
    } catch {
      patch(item.id, { status: "error", message: t("inbox.apiUnreachable"), include: false });
    }
  }

  // Read files two or three at a time, in the order they were added.
  useEffect(() => {
    const running = items.filter((i) => i.status === "analysing").length;
    const next = items.filter((i) => i.status === "queued").slice(0, Math.max(0, CONCURRENCY - running));
    if (next.length === 0) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- marks queue entries as started; the work itself is async
    setItems((prev) => prev.map((i) => (next.some((n) => n.id === i.id) ? { ...i, status: "analysing" } : i)));
    next.forEach((i) => void analyse(i));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- analyse only reads stable props and setters
  }, [items]);

  async function sendAi(item: InboxItem) {
    patch(item.id, { status: "ai_reading", confirmAi: false, message: null });
    try {
      const body = new FormData();
      body.append("file", item.file!);
      const res = await fetch("/api/labs/upload", { method: "POST", body });
      if (res.status === 409) { patch(item.id, { status: "already_saved", kind: "lab", message: null }); return; }
      if (!res.ok) { patch(item.id, { status: "needs_ai", message: `${t("inbox.aiFailed")} ${await errorMessage(res, "")}`.trim() }); return; }
      const draft = (await res.json()) as UploadDraft;
      const suggested = nearestRecord(records, draft.test_date);
      patch(item.id, {
        status: "review", kind: "lab", readBy: "ai", rows: draft.rows.length ? draft.rows.map(rowFromDraft) : [emptyRow()], open: true,
        date: draft.test_date ?? "", lab: draft.lab_name, suggested, record: suggested ? String(suggested.id) : "new",
        message: draft.rows.length ? null : t("inbox.noRowsRead"),
      });
    } catch {
      patch(item.id, { status: "needs_ai", message: t("inbox.apiUnreachable") });
    }
  }

  const sendable = items.filter(savable);
  const reading = items.filter((i) => i.status === "queued" || i.status === "analysing" || i.status === "ai_reading").length;
  const doneAt = items.filter((i) => i.status === "analysing" || i.status === "queued").length;
  const total = items.filter((i) => i.file).length;

  async function saveAll() {
    setNotice(null);
    const marked = new Map<string, string>();
    const toSend: InboxItem[] = [];
    for (const item of sendable) {
      const filled = item.rows.filter((r) => !isBlank(r));
      if (isLabItem(item) && item.status !== "already_saved") {
        const problems = [...(item.date ? [] : [t("inbox.needDate")]), ...(filled.length ? rowProblems(filled, t) : [t("inbox.needRows")])];
        if (problems.length) { marked.set(item.id, problems.join(" ")); continue; }
      }
      toSend.push(item);
    }
    setItems((prev) => prev.map((i) => (marked.has(i.id) ? { ...i, message: marked.get(i.id)!, open: true } : i.message && !marked.has(i.id) && i.status === "review" ? { ...i, message: null } : i)));
    if (toSend.length === 0) { if (marked.size) setNotice(t("inbox.fixFirst")); return; }
    setSaving(true);
    try {
      const results = new Map<string, Partial<InboxItem>>();
      const files = toSend.filter((i) => i.file);
      if (files.length) {
        const res = await fetch("/api/inbox/confirm", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: files.map((i) => ({
            file_hash: i.hash, kind: i.kind, filename: i.name, test_date: i.date || null, lab_name: i.lab,
            rows: isLabItem(i) && i.status !== "already_saved" ? toPayload(i.rows.filter((r) => !isBlank(r))) : [],
            record_id: i.record === "new" ? null : Number(i.record), title: i.record === "new" ? i.title.trim() || null : null,
          })) }),
        });
        if (!res.ok) throw new Error(await errorMessage(res, t("inbox.apiUnreachable")));
        const { results: out } = (await res.json()) as { results: ItemResult[] };
        files.forEach((i, n) => {
          const r = out[n];
          results.set(i.id, r && r.status !== "error"
            ? { status: "saved", recordId: r.record_id, message: null, include: false }
            : { status: "error", message: r?.message ?? t("inbox.analyseFailed") });
        });
      }
      for (const i of toSend.filter((x) => !x.file)) {
        const res = await fetch("/api/labs/manual", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ test_date: i.date, lab_name: i.lab, rows: toPayload(i.rows.filter((r) => !isBlank(r))) }),
        });
        results.set(i.id, res.ok ? { status: "saved", message: null, include: false } : { status: "error", message: await errorMessage(res, t("inbox.analyseFailed")) });
      }
      setItems((prev) => prev.map((i) => (results.has(i.id) ? { ...i, ...results.get(i.id)! } : i)));
      const saved = [...results.values()].filter((r) => r.status === "saved").length;
      const failed = results.size - saved + marked.size;
      setNotice([saved ? tp("inbox.savedCount", saved) : "", failed ? tp("inbox.failedCount", failed) : ""].filter(Boolean).join(". ") + ".");
    } catch (e) {
      setNotice(e instanceof Error && e.message ? e.message : t("inbox.apiUnreachable"));
    } finally {
      setSaving(false);
    }
  }

  const allSaved = items.length > 0 && items.every((i) => i.status === "saved");
  return (
    <div className="space-y-6">
      <datalist id={listId}>{markerNames.map((n) => <option key={n} value={n} />)}</datalist>
      <InboxDropZone onFiles={addFiles} />
      <p className="max-w-prose text-sm text-muted-foreground">{t("inbox.privacy")}</p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <Button type="button" variant="outline" size="sm" onClick={addManual}><Plus aria-hidden /> {t("inbox.addManual")}</Button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={ask} onChange={(e) => setAsk(e.target.checked)} className="size-4 accent-[var(--data)]" />
          {t("inbox.askBeforeAi")}
        </label>
      </div>
      {skipped.length > 0 && (
        <ul role="alert" className="space-y-1 text-sm text-outrange">{skipped.map((n, i) => <li key={`${n}-${i}`}>{t("inbox.badFileType", { name: n })}</li>)}</ul>
      )}

      {items.length > 0 && (
        <section className="space-y-4" aria-label={t("inbox.filesCount", { n: items.length })}>
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {tp("inbox.filesCount", items.length)}
            {reading > 0 ? ` · ${tp("inbox.stillReading", reading)}` : ""}
            {doneAt > 0 && total > 0 ? ` · ${t("inbox.analysingProgress", { done: total - doneAt + 1, total })}` : ""}
          </p>
          <ul className="space-y-3">
            {items.map((item) => (
              <InboxItemCard key={item.id} item={item} records={records} askBeforeAi={ask} markerListId={listId}
                onChange={(change) => patch(item.id, change)}
                onRemove={() => setItems((prev) => prev.filter((i) => i.id !== item.id))}
                onSendAi={() => void sendAi(item)} />
            ))}
          </ul>
          <div className="sticky bottom-3 space-y-2 rounded-2xl border border-border bg-card p-3 shadow-card">
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={saveAll} disabled={saving || sendable.length === 0 || reading > 0}>
                {saving ? t("inbox.saving") : tp("inbox.saveAll", sendable.length)}
              </Button>
              {allSaved && (
                <>
                  <Link href="/biomarkers" className="text-sm underline underline-offset-4">{t("inbox.openBiomarkers")}</Link>
                  <Button variant="ghost" onClick={() => { setItems([]); setNotice(null); }}>{t("inbox.addMore")}</Button>
                </>
              )}
            </div>
            <p aria-live="polite" className="text-sm text-muted-foreground">{notice ?? t("inbox.nothingYet")}</p>
          </div>
        </section>
      )}
    </div>
  );
}
