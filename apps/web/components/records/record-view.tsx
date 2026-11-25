"use client";
import { useCallback, useState } from "react";
import { ScanPanel } from "@/components/organs/scan-panel";
import { getJson } from "@/lib/request";
import type { RecordDetail } from "@/lib/types";
import { DetailsSection } from "./details-section";
import { DiagnosesSection } from "./diagnoses-section";
import { FilesSection } from "./files-section";
import { QuestionsSection, NotesSection } from "./notes-section";
import { RecordHeader } from "./record-header";
import { TreatmentsSection } from "./treatments-section";

/** The record page. Every change goes to the API and then re-reads the record, so what you see is what is stored. */
export function RecordView({ initial, focusNote }: { initial: RecordDetail; focusNote: boolean }) {
  const [rec, setRec] = useState(initial);
  const reload = useCallback(async () => { setRec(await getJson<RecordDetail>(`records/${initial.id}`)); }, [initial.id]);
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <RecordHeader rec={rec} reload={reload} />
      <NotesSection recordId={rec.id} items={rec.notes} reload={reload} focus={focusNote} />
      <DiagnosesSection recordId={rec.id} items={rec.diagnoses} reload={reload} />
      <TreatmentsSection recordId={rec.id} items={rec.treatments} reload={reload} />
      <QuestionsSection recordId={rec.id} items={rec.notes} reload={reload} />
      <FilesSection recordId={rec.id} items={rec.attachments} reload={reload} />
      <DetailsSection rec={rec} reload={reload} />
      {rec.record_type === "imaging" && <ScanPanel recordId={rec.id} />}
    </div>
  );
}
