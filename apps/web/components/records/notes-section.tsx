"use client";
import { useEffect, useRef, useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { todayIso } from "@/lib/format-date";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { RecordNote } from "@/lib/types";
import { ConfirmDelete } from "./confirm-delete";
import { ErrorLine, inputClass, SectionCard, useAction } from "./kit";

export function NotesSection({ recordId, items, reload, focus }: { recordId: number; items: RecordNote[]; reload: () => Promise<void>; focus: boolean }) {
  const { t, formatDate } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [editDate, setEditDate] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const notes = items.filter((n) => n.kind === "note").sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "") || b.id - a.id);

  // Arriving from "Add a note" on the Overview: land on the box, ready to type.
  useEffect(() => {
    if (!focus) return;
    box.current?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    box.current?.focus({ preventScroll: true });
  }, [focus]);

  async function add() {
    const value = text.trim();
    if (!value) return;
    if (await run(() => sendJson(`records/${recordId}/notes`, "POST", { text: value, date: todayIso(), kind: "note" }))) { setText(""); box.current?.focus(); }
  }
  async function saveEdit(id: number) {
    if (!editText.trim()) { setError(t("records.needText")); return; }
    if (await run(() => sendJson(`notes/${id}`, "PATCH", { text: editText.trim(), date: editDate || undefined }))) setEditing(null);
  }
  return (
    <SectionCard id="notes" title={t("records.notesTitle")} count={notes.length}>
      <div className="space-y-2">
        <label htmlFor="note-box" className="block text-sm font-medium">{t("records.notePrompt")}</label>
        <Textarea id="note-box" ref={box} rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("records.notePh")}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void add(); } }} />
        <Button type="button" size="lg" className="h-12 w-full sm:w-auto" disabled={busy || !text.trim()} onClick={add}><Plus aria-hidden />{t("records.addNote")}</Button>
      </div>
      <ErrorLine message={error} />
      {notes.length === 0 ? <p className="empty-state p-4 text-sm text-muted-foreground">{t("records.notesEmpty")}</p> : (
        <ul className="space-y-2">
          {notes.map((n) => (
            <li key={n.id} className="min-w-0 rounded-2xl border bg-card/60 p-3">
              {editing === n.id ? (
                <div className="space-y-3">
                  <Textarea aria-label={t("records.notePrompt")} rows={3} value={editText} onChange={(e) => setEditText(e.target.value)} autoFocus />
                  <Input type="date" aria-label={t("records.fDate")} className={inputClass} value={editDate} onChange={(e) => setEditDate(e.target.value)} />
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" size="lg" disabled={busy} onClick={() => saveEdit(n.id)}>{t("records.save")}</Button>
                    <Button type="button" size="lg" variant="outline" onClick={() => setEditing(null)}>{t("records.cancel")}</Button>
                  </div>
                </div>
              ) : (
                <div className="flex min-w-0 items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="tnum text-xs font-medium text-muted-foreground">{n.date ? formatDate(n.date, { day: "numeric", month: "long" }) : t("common.noDate")}</p>
                    <p className="mt-0.5 whitespace-pre-line break-words">{n.text}</p>
                  </div>
                  <Button type="button" variant="ghost" size="icon-lg" className="size-11" aria-label={t("records.edit")} onClick={() => { setEditing(n.id); setEditText(n.text); setEditDate(n.date ?? ""); setError(null); }}><Pencil aria-hidden /></Button>
                  <ConfirmDelete label={t("records.delete")} question={t("records.confirmNote")} disabled={busy} onConfirm={() => run(() => sendJson(`notes/${n.id}`, "DELETE"))} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function QuestionsSection({ recordId, items, reload }: { recordId: number; items: RecordNote[]; reload: () => Promise<void> }) {
  const { t } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [text, setText] = useState("");
  const [answering, setAnswering] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const qs = items.filter((n) => n.kind === "question");
  const open = qs.filter((q) => !q.done);
  const done = qs.filter((q) => q.done);

  async function add() {
    const value = text.trim();
    if (!value) return;
    if (await run(() => sendJson(`records/${recordId}/notes`, "POST", { text: value, kind: "question" }))) setText("");
  }
  async function addAnswer(q: RecordNote) {
    if (!answer.trim()) { setError(t("records.needText")); return; }
    if (await run(() => sendJson(`records/${recordId}/notes`, "POST", { text: `${q.text} — ${answer.trim()}`, date: todayIso(), kind: "note" }))) { setAnswering(null); setAnswer(""); }
  }
  const row = (q: RecordNote) => (
    <li key={q.id} className="min-w-0 rounded-2xl border bg-card/60 p-1.5">
      <div className="flex min-w-0 items-center gap-1">
        <label className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-xl px-2">
          <input type="checkbox" checked={q.done} disabled={busy} onChange={() => run(() => sendJson(`notes/${q.id}`, "PATCH", { done: !q.done }))} className="size-5 shrink-0 accent-[var(--primary)]" />
          <span className={`min-w-0 break-words ${q.done ? "text-muted-foreground line-through" : ""}`}>{q.text}</span>
        </label>
        <ConfirmDelete label={t("records.delete")} question={t("records.confirmQuestion")} disabled={busy} onConfirm={() => run(() => sendJson(`notes/${q.id}`, "DELETE"))} />
      </div>
      {q.done && (answering === q.id ? (
        <div className="flex flex-wrap items-center gap-2 px-2 pb-2">
          <Input aria-label={t("records.answerPrompt")} placeholder={t("records.answerPrompt")} className={`${inputClass} min-w-0 flex-1`} value={answer} onChange={(e) => setAnswer(e.target.value)} autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void addAnswer(q); } }} />
          <Button type="button" size="lg" disabled={busy} onClick={() => addAnswer(q)}>{t("records.addNote")}</Button>
          <Button type="button" size="lg" variant="outline" onClick={() => setAnswering(null)}>{t("records.cancel")}</Button>
        </div>
      ) : (
        <Button type="button" variant="ghost" size="lg" className="ml-1" onClick={() => { setAnswering(q.id); setAnswer(""); setError(null); }}>{t("records.answerToNote")}</Button>
      ))}
    </li>
  );
  return (
    <SectionCard id="questions" title={t("records.qTitle")} count={open.length}>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <Input aria-label={t("records.addQuestion")} placeholder={t("records.qPh")} className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" size="lg" disabled={busy || !text.trim()}><Plus aria-hidden />{t("records.add")}</Button>
      </form>
      <ErrorLine message={error} />
      {qs.length === 0 && <p className="empty-state p-4 text-sm text-muted-foreground">{t("records.qEmpty")}</p>}
      {open.length > 0 && <ul className="space-y-2">{open.map(row)}</ul>}
      {done.length > 0 && (
        <div className="space-y-2">
          <h3 className="eyebrow">{t("records.answered")}</h3>
          <ul className="space-y-2">{done.map(row)}</ul>
        </div>
      )}
    </SectionCard>
  );
}
