import type { OrganCatalogEntry, ScanExtractReport, ScanMeasurementRow, ScanOrigin, ScanSide, ScanTags } from "@/lib/types";

export const MAX_VALUE = 100000;
export const MAX_TEXT = 200;

/** What the server holds for a box: the exact number or wording, so an untouched box is sent back unchanged. */
export type Stored = { value: number | null; value_text: string | null };
/** One editable box: what is typed, where the stored value came from, whether the owner has verified it, and the
 * stored value itself (`null` for a box typed here). The text is only the display of `stored` until `edited`. */
export type Cell = { text: string; origin: ScanOrigin; verified: boolean; edited: boolean; stored: Stored | null };
export type Draft = Record<string, Cell>;
export type Param = OrganCatalogEntry["params"][number];

export const cellKey = (organ: string, param: string, side: ScanSide) => `${organ}|${param}|${side}`;

/** Draft from stored rows; `fmt` writes numbers the way the visitor's language does (8,2 in Russian). */
export function draftFromRows(rows: ScanMeasurementRow[], fmt: (n: number) => string): Draft {
  const out: Draft = {};
  for (const r of rows) {
    const text = r.value !== null ? fmt(r.value) : (r.value_text ?? "");
    out[cellKey(r.organ_key, r.param_key, r.side)] = {
      text, origin: r.origin, verified: r.verified, edited: false, stored: { value: r.value, value_text: r.value_text },
    };
  }
  return out;
}

/** After a read: server rows win, except boxes the owner changed and has not saved yet. */
export function mergeServer(local: Draft, server: Draft): Draft {
  const out = { ...server };
  for (const [k, c] of Object.entries(local)) if (c.edited) out[k] = c;
  return out;
}

export type Parsed = { kind: "empty" } | { kind: "ok"; value: number } | { kind: "bad" };

/** "8,2" and "8.2" are the same number; anything that is not a plain non-negative number is rejected. */
export function parseNumber(text: string): Parsed {
  const s = text.trim().replace(/\s/g, "");
  if (!s) return { kind: "empty" };
  if (!/^\d+([.,]\d+)?$|^[.,]\d+$/.test(s)) return { kind: "bad" };
  const n = Number(s.replace(",", "."));
  return Number.isFinite(n) && n >= 0 && n <= MAX_VALUE ? { kind: "ok", value: n } : { kind: "bad" };
}

export type PutBody = { organs: string[]; measurements: { organ_key: string; param_key: string; side: ScanSide; value?: number; value_text?: string }[] };

/** Body for PUT /scans/{id}, or the keys of boxes that hold a bad number. Empty boxes are left out, never sent as 0.
 * A box the owner did not touch sends its stored value exactly, never the rounded text it shows. */
export function buildPut(organs: string[], catalog: OrganCatalogEntry[], draft: Draft): { body: PutBody } | { bad: string[] } {
  const bad: string[] = [];
  const measurements: PutBody["measurements"] = [];
  for (const o of organs) {
    for (const p of catalog.find((c) => c.key === o)?.params ?? []) {
      for (const side of (p.sides ? ["left", "right"] : [""]) as ScanSide[]) {
        const key = cellKey(o, p.key, side);
        const cell = draft[key];
        if (!cell) continue;
        if (!cell.edited && cell.stored) {
          const { value, value_text } = cell.stored;
          if (p.kind === "text" && value_text) { measurements.push({ organ_key: o, param_key: p.key, side, value_text }); continue; }
          if (p.kind === "numeric" && value !== null) { measurements.push({ organ_key: o, param_key: p.key, side, value }); continue; }
        }
        if (!cell.text.trim()) continue;
        if (p.kind === "text") { measurements.push({ organ_key: o, param_key: p.key, side, value_text: cell.text.trim() }); continue; }
        const n = parseNumber(cell.text);
        if (n.kind === "ok") measurements.push({ organ_key: o, param_key: p.key, side, value: n.value });
        else bad.push(key);
      }
    }
  }
  return bad.length ? { bad } : { body: { organs, measurements } };
}

/** Boxes of one organ that hold something; removing the organ deletes them on Save. */
export function filledCells(organ: string, draft: Draft): number {
  return Object.entries(draft).filter(([k, c]) => k.startsWith(`${organ}|`) && c.text.trim()).length;
}

/** Everything a read touched on this record, so "no change" can be told apart from "nothing found". */
export const changed = (r: ScanExtractReport) => r.added + r.updated > 0;

export const tagKeys = (tags: ScanTags) => tags.organs.map((o) => o.organ_key);
