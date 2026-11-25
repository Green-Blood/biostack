"use client";
import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { sendJson } from "@/lib/request";
import type { RecordTreatment } from "@/lib/types";
import { ConfirmDelete } from "./confirm-delete";
import { emptyTx, ROUTES, TreatmentFields, txBody, txFrom, type TxDraft } from "./fields";
import { ErrorLine, SectionCard, useAction } from "./kit";

const ORDER: RecordTreatment["status"][] = ["active", "planned", "undated", "finished"];
const STATUS: Record<RecordTreatment["status"], Key> = { active: "records.txActive", planned: "records.txPlanned", finished: "records.txFinished", undated: "records.txUndated" };

export function TreatmentsSection({ recordId, items, reload }: { recordId: number; items: RecordTreatment[]; reload: () => Promise<void> }) {
  const { t, formatDate } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<TxDraft>(emptyTx(0));
  const presets = ROUTES.map((k) => t(k));
  const sorted = [...items].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  const day = (iso: string) => formatDate(iso, { day: "numeric", month: "short" });

  const open = (id: number | "new", d: TxDraft) => { setEditing(id); setDraft(d); setError(null); };
  async function save() {
    if (!draft.name.trim()) { setError(t("records.needName")); return; }
    if (draft.start && draft.end && draft.end < draft.start) { setError(t("records.endBeforeStart")); return; }
    const ok = await run(() => editing === "new" ? sendJson(`records/${recordId}/treatments`, "POST", txBody(draft)) : sendJson(`treatments/${editing}`, "PATCH", txBody(draft)));
    if (ok) setEditing(null);
  }
  const form = (
    <div className="space-y-3 rounded-2xl border bg-card/60 p-3">
      <TreatmentFields value={draft} onChange={setDraft} autoFocus />
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="lg" disabled={busy} onClick={save}>{busy ? t("records.saving") : t("records.save")}</Button>
        <Button type="button" size="lg" variant="outline" onClick={() => setEditing(null)}>{t("records.cancel")}</Button>
      </div>
    </div>
  );
  return (
    <SectionCard id="treatment" title={t("records.txTitle")} count={items.length}>
      <ErrorLine message={error} />
      {items.length === 0 && editing !== "new" && <p className="empty-state p-4 text-sm text-muted-foreground">{t("records.txEmpty")}</p>}
      <ul className="space-y-2">
        {sorted.map((x) => {
          const line = [x.dosage, x.route, x.frequency].filter(Boolean).join(" · ");
          const dates = x.start_date ? (x.end_date ? t("records.range", { from: day(x.start_date), to: day(x.end_date) }) : t("records.fromDate", { from: day(x.start_date) })) : x.end_date ? t("records.untilDate", { to: day(x.end_date) }) : "";
          return (
            <li key={x.id} className="min-w-0">
              {editing === x.id ? form : (
                <div className="flex min-w-0 items-start gap-2 rounded-2xl border bg-card/60 p-3">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="break-words font-medium">{x.name}</p>
                    <span className="inline-flex h-6 items-center rounded-full border bg-secondary px-2.5 text-xs font-medium text-secondary-foreground">{t(STATUS[x.status])}</span>
                    {line && <p className="break-words text-sm">{line}</p>}
                    {dates && <p className="tnum text-sm text-muted-foreground">{dates}</p>}
                    {x.notes && <p className="break-words text-sm text-muted-foreground">{x.notes}</p>}
                  </div>
                  {x.editable && (
                    <>
                      <Button type="button" variant="ghost" size="icon-lg" className="size-11" aria-label={t("records.edit")} onClick={() => open(x.id, txFrom(x, presets))}><Pencil aria-hidden /></Button>
                      <ConfirmDelete label={t("records.delete")} question={t("records.confirmTx")} disabled={busy} onConfirm={() => run(() => sendJson(`treatments/${x.id}`, "DELETE"))} />
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {editing === "new" ? form : <Button type="button" variant="outline" size="lg" onClick={() => open("new", emptyTx(0))}><Plus aria-hidden />{t("records.addTreatment")}</Button>}
    </SectionCard>
  );
}
