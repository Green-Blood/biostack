"use client";
import { useState } from "react";
import { CircleCheck, CircleHelp, CircleSlash, Pencil, Plus, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { Diagnosis, DiagnosisStatus } from "@/lib/types";
import { ConfirmDelete } from "./confirm-delete";
import { DiagnosisFields, DX_STATUSES, dxBody, dxFrom, emptyDx, type DxDraft } from "./fields";
import { ErrorLine, SectionCard, useAction } from "./kit";

const ICON: Record<DiagnosisStatus, LucideIcon> = { suspected: CircleHelp, confirmed: CircleCheck, ruled_out: CircleSlash };

export function DiagnosisChip({ status }: { status: DiagnosisStatus | null }) {
  const { t } = useI18n();
  if (!status) return null;
  const Icon = ICON[status];
  const label = DX_STATUSES.find((s) => s.value === status)!.label;
  return <span className="inline-flex h-6 items-center gap-1 rounded-full border bg-secondary px-2.5 text-xs font-medium text-secondary-foreground"><Icon className="size-3" aria-hidden />{t(label)}</span>;
}

export function DiagnosesSection({ recordId, items, reload }: { recordId: number; items: Diagnosis[]; reload: () => Promise<void> }) {
  const { t } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<DxDraft>(emptyDx(0));

  const open = (id: number | "new", d: DxDraft) => { setEditing(id); setDraft(d); setError(null); };
  async function save() {
    if (!draft.name.trim()) { setError(t("records.needName")); return; }
    const ok = await run(() => editing === "new" ? sendJson(`records/${recordId}/diagnoses`, "POST", dxBody(draft)) : sendJson(`diagnoses/${editing}`, "PATCH", dxBody(draft)));
    if (ok) setEditing(null);
  }
  const form = (
    <div className="space-y-3 rounded-2xl border bg-card/60 p-3">
      <DiagnosisFields value={draft} onChange={setDraft} autoFocus />
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="lg" disabled={busy} onClick={save}>{busy ? t("records.saving") : t("records.save")}</Button>
        <Button type="button" size="lg" variant="outline" onClick={() => setEditing(null)}>{t("records.cancel")}</Button>
      </div>
    </div>
  );
  return (
    <SectionCard id="diagnoses" title={t("records.dxTitle")} count={items.length}>
      <ErrorLine message={error} />
      {items.length === 0 && editing !== "new" && <p className="empty-state p-4 text-sm text-muted-foreground">{t("records.dxEmpty")}</p>}
      <ul className="space-y-2">
        {items.map((d) => (
          <li key={d.id} className="min-w-0">
            {editing === d.id ? form : (
              <div className="flex min-w-0 items-start gap-2 rounded-2xl border bg-card/60 p-3">
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="break-words font-medium">{d.name}{d.icd10 && <span className="tnum ml-2 text-sm font-normal text-muted-foreground">{d.icd10}</span>}</p>
                  <DiagnosisChip status={d.status} />
                  {d.note && <p className="break-words text-sm text-muted-foreground">{d.note}</p>}
                </div>
                <Button type="button" variant="ghost" size="icon-lg" className="size-11" aria-label={t("records.edit")} onClick={() => open(d.id, dxFrom(d))}><Pencil aria-hidden /></Button>
                <ConfirmDelete label={t("records.delete")} question={t("records.confirmDx")} disabled={busy} onConfirm={() => run(() => sendJson(`diagnoses/${d.id}`, "DELETE"))} />
              </div>
            )}
          </li>
        ))}
      </ul>
      {editing === "new" ? form : <Button type="button" variant="outline" size="lg" onClick={() => open("new", emptyDx(0))}><Plus aria-hidden />{t("records.addDiagnosis")}</Button>}
    </SectionCard>
  );
}
