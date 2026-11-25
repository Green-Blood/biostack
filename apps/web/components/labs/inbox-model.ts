import { isBlank, parseNumber, type EditableRow } from "@/lib/lab-rows";
import type { T } from "@/lib/i18n/translate";
import type { UploadDraft } from "@/lib/types";

export type Kind = "lab" | "imaging_report" | "other";
export type Status = "queued" | "analysing" | "review" | "ready" | "needs_ai" | "ai_reading" | "already_saved" | "error" | "saved" | "not_saved";
export type RecordRef = { id: number; title: string; date: string | null };

/** What POST /inbox/analyze returns. */
export type Analysis = {
  file_hash: string; filename: string; kind: Kind; needs_ai: boolean; draft: UploadDraft | null;
  already_saved: { report_id: number } | null; suggested_record: RecordRef | null;
};
export type ItemResult = { file_hash: string; status: "saved" | "already_saved" | "error"; record_id: number | null; report_id?: number | null; message?: string | null };

export type InboxItem = {
  id: string;
  file: File | null; // null: results typed by hand
  name: string;
  status: Status;
  kind: Kind;
  hash: string;
  readBy: "local" | "ai" | null;
  rows: EditableRow[];
  date: string;
  lab: string;
  record: string; // "new" or a record id
  suggested: RecordRef | null;
  title: string;
  include: boolean;
  open: boolean;
  confirmAi: boolean;
  message: string | null;
  recordId: number | null;
  thumb: string | null;
};

export const hasRows = (item: InboxItem) => item.rows.some((r) => !isBlank(r));
export const isLabItem = (item: InboxItem) => item.kind === "lab" || item.file === null;
/** States the owner can save from. */
export const savable = (item: InboxItem) => item.include && ["review", "ready", "needs_ai", "already_saved", "error"].includes(item.status) && (item.status !== "error" || item.hash !== "");

export function rowProblems(rows: EditableRow[], t: T): string[] {
  const out: string[] = [];
  rows.forEach((r, i) => {
    const n = i + 1;
    const label = r.name.trim() || t("labs.rowN", { n });
    const nums = [parseNumber(r.value), parseNumber(r.refMin), parseNumber(r.refMax)];
    if (!r.name.trim()) out.push(t("labs.needName", { n }));
    else if (nums.some((x) => x !== null && Number.isNaN(x))) out.push(t("labs.needNumbers", { label }));
    else if (nums[0] === null && !r.text.trim()) out.push(t("labs.needValue", { label }));
    else if (nums[1] !== null && nums[2] !== null && nums[1] > nums[2]) out.push(t("labs.rangeInverted", { label }));
  });
  return out;
}

export const ACCEPTED_NAME = /\.(pdf|jpe?g|png|heic)$/i;
export const ACCEPTED_TYPE = /^(application\/pdf|image\/(jpeg|png|heic))$/;
export const isAccepted = (f: File) => ACCEPTED_NAME.test(f.name) || ACCEPTED_TYPE.test(f.type);
