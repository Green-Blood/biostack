import type { DraftRow, NeedsProfile } from "@/lib/types";

/** A result row as typed in the review table: every field is text until it is sent. */
export type EditableRow = {
  id: string; name: string; value: string; unit: string; refMin: string; refMax: string; text: string;
  /** Why the API left the reference range blank (sex/age missing from the profile); read-only, never sent back. */
  needsProfile?: NeedsProfile | null;
};

export type LabPayloadRow = {
  name: string; value: number | null; unit: string; ref_min: number | null; ref_max: number | null; result_text: string | null;
};

let counter = 0;
export const newRowId = () => `row-${++counter}`;

export const emptyRow = (): EditableRow => ({ id: newRowId(), name: "", value: "", unit: "", refMin: "", refMax: "", text: "" });

const asText = (n: number | null) => (n === null ? "" : String(n));

export const rowFromDraft = (r: DraftRow): EditableRow => ({
  id: newRowId(), name: r.name, value: asText(r.value), unit: r.unit, refMin: asText(r.ref_min), refMax: asText(r.ref_max), text: r.result_text ?? "", needsProfile: r.needs_profile ?? null,
});

/** Parses "28,5" or "28.5"; blank is null; anything else is NaN. */
export function parseNumber(s: string): number | null {
  const t = s.trim().replace(",", ".");
  return t === "" ? null : Number(t);
}

export function outOfRange(row: EditableRow): boolean | null {
  const v = parseNumber(row.value), lo = parseNumber(row.refMin), hi = parseNumber(row.refMax);
  if (v === null || Number.isNaN(v)) return null;
  return (lo !== null && !Number.isNaN(lo) && v < lo) || (hi !== null && !Number.isNaN(hi) && v > hi);
}

export function isBlank(row: EditableRow): boolean {
  return [row.name, row.value, row.unit, row.refMin, row.refMax, row.text].every((f) => f.trim() === "");
}

export const toPayload = (rows: EditableRow[]): LabPayloadRow[] =>
  rows.map((r) => ({
    name: r.name.trim(), value: parseNumber(r.value), unit: r.unit.trim(),
    ref_min: parseNumber(r.refMin), ref_max: parseNumber(r.refMax), result_text: r.text.trim() || null,
  }));
