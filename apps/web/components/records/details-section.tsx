"use client";
import { useState } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { RecordDetail } from "@/lib/types";
import { ErrorLine, Field, SectionCard, useAction } from "./kit";

export function DetailsSection({ rec, reload }: { rec: RecordDetail; reload: () => Promise<void> }) {
  const { t } = useI18n();
  const { busy, error, setError, run } = useAction(reload);
  const [editing, setEditing] = useState(false);
  const [details, setDetails] = useState("");
  const [note, setNote] = useState("");
  const empty = !rec.details && !rec.doctors_note;
  if (empty && !rec.is_manual) return null;
  async function save() {
    if (await run(() => sendJson(`records/${rec.id}`, "PATCH", { details, doctors_note: note }))) setEditing(false);
  }
  return (
    <SectionCard id="details" title={t("records.detailsTitle")} defaultOpen={!empty}>
      <ErrorLine message={error} />
      {editing ? (
        <div className="space-y-3">
          <Field label={t("records.fNotes")}>{(id) => <Textarea id={id} rows={4} value={details} onChange={(e) => setDetails(e.target.value)} autoFocus />}</Field>
          <Field label={t("records.fDoctorsNote")}>{(id) => <Textarea id={id} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="lg" disabled={busy} onClick={save}>{busy ? t("records.saving") : t("records.save")}</Button>
            <Button type="button" size="lg" variant="outline" onClick={() => setEditing(false)}>{t("records.cancel")}</Button>
          </div>
        </div>
      ) : (
        <>
          {empty && <p className="empty-state p-4 text-sm text-muted-foreground">{t("records.detailsEmpty")}</p>}
          {rec.details && <p className="whitespace-pre-line break-words">{rec.details}</p>}
          {rec.doctors_note && <p className="whitespace-pre-line break-words border-t pt-3"><span className="font-medium">{t("timeline.doctorsNote")} </span>{rec.doctors_note}</p>}
          {rec.is_manual && <Button type="button" variant="outline" size="lg" onClick={() => { setDetails(rec.details); setNote(rec.doctors_note); setError(null); setEditing(true); }}><Pencil aria-hidden />{t("records.edit")}</Button>}
        </>
      )}
    </SectionCard>
  );
}
