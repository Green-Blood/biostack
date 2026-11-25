import { Bed, FileText, FlaskConical, ScanLine, Scissors, Stethoscope, type LucideIcon } from "lucide-react";
import type { RecordKind } from "@/lib/types";
import type { Key } from "@/lib/i18n/translate";

export const KIND_META: Record<RecordKind, { label: Key; Icon: LucideIcon }> = {
  visit: { label: "records.kindVisit", Icon: Stethoscope },
  hospital_stay: { label: "records.kindStay", Icon: Bed },
  procedure: { label: "records.kindProcedure", Icon: Scissors },
  lab: { label: "records.kindLab", Icon: FlaskConical },
  imaging: { label: "records.kindImaging", Icon: ScanLine },
  other: { label: "records.kindOther", Icon: FileText },
};

export const kindOf = (s: string): RecordKind => (s in KIND_META ? (s as RecordKind) : "other");

type Fmt = {
  t: (k: Key, p?: Record<string, string | number>) => string;
  tp: (k: Key, n: number, p?: Record<string, string | number>) => string;
  formatDate: (iso: string, o?: Intl.DateTimeFormatOptions) => string;
};
type Span = { record_type: string; date: string | null; end_date?: string | null; status?: string | null; stay_days?: number | null };

export const isOngoing = (r: Span) => r.status === "ongoing" || (r.record_type === "hospital_stay" && !r.end_date && r.status !== "completed");

/** "11 Nov – today · day 3", "11 Nov – 21 Nov · 10 days", or (short) "from 11 Nov · ongoing". */
export function spanLabel(r: Span, f: Fmt, short = false): string {
  const day = (iso: string) => f.formatDate(iso, { day: "numeric", month: "short" });
  if (!r.date) return f.t("common.noDate");
  if (isOngoing(r)) {
    if (short) return f.t("records.rangeFromOngoing", { from: day(r.date) });
    return r.stay_days != null ? f.t("records.rangeOngoingDay", { from: day(r.date), n: r.stay_days }) : f.t("records.rangeOngoing", { from: day(r.date) });
  }
  if (r.end_date && r.end_date !== r.date) {
    const base = f.t("records.range", { from: day(r.date), to: day(r.end_date) });
    return r.stay_days != null ? `${base} · ${f.tp("records.days", r.stay_days)}` : base;
  }
  return day(r.date);
}
