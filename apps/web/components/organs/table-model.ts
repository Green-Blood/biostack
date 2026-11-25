import type { Context, OrganDetail, OrganSeries, ScanColumn } from "@/lib/types";

export type WindowKind = "last5" | "lastYear" | "all";
export type Param = OrganDetail["params"][number];
export type RowGroup = { param_key: string; rows: Param[] };
export type YearGroup = { year: string | null; span: number };

const DAY_MS = 86_400_000;

/** Show the window selector only when it changes something; default to the last 5 scans when there are many. */
export const WINDOW_THRESHOLD = 5;
export const defaultWindow = (count: number): WindowKind => (count > 8 ? "last5" : "all");

/** Columns to show, oldest first. "Last year" means the 12 months up to the latest dated scan, so it is never empty. */
export function windowScans(scans: ScanColumn[], kind: WindowKind): ScanColumn[] {
  if (kind === "last5") return scans.slice(-5);
  if (kind === "lastYear") {
    const dated = scans.filter((s) => s.date);
    const latest = dated.at(-1)?.date;
    if (!latest) return scans;
    const from = Date.parse(latest) - 365 * DAY_MS;
    return dated.filter((s) => Date.parse(s.date!) >= from);
  }
  return scans;
}

/** Consecutive columns of the same year share one header cell; undated scans form their own group. */
export function yearGroups(scans: ScanColumn[]): YearGroup[] {
  const out: YearGroup[] = [];
  for (const s of scans) {
    const year = s.date ? s.date.slice(0, 4) : null;
    const last = out.at(-1);
    if (last && last.year === year) last.span++;
    else out.push({ year, span: 1 });
  }
  return out;
}

/** Rows grouped by parameter (sides become sub-rows), keeping the API's catalog order. */
export function rowGroups(params: Param[]): RowGroup[] {
  const out: RowGroup[] = [];
  for (const p of params) {
    const last = out.at(-1);
    if (last && last.param_key === p.param_key) last.rows.push(p);
    else out.push({ param_key: p.param_key, rows: [p] });
  }
  return out;
}

/** The events drawn under every chart: visits, the scans themselves and treatment courses (optionally only related ones). */
export function buildContext(organ: OrganDetail, relatedOnly: boolean): Context {
  const scans = organ.scans
    .filter((s) => s.date)
    .map((s) => ({ id: s.record_id, date: s.date!, title: s.title, record_type: "imaging", is_demo: false }));
  const visits = organ.visits.map((v) => ({ id: v.id, date: v.date, title: v.title, record_type: v.record_type, is_demo: false }));
  return {
    medications: organ.treatments.filter((tr) => !relatedOnly || tr.related)
      .map((tr) => ({ name: tr.name, dosage: tr.dosage ?? "", start: tr.start, end: tr.end })),
    records: [...visits, ...scans].sort((a, b) => a.date.localeCompare(b.date)),
  };
}

export type UnverifiedPoint = { record_id: number; date: string };

/** The charted points of one series whose value the owner has not verified yet, oldest first. */
export function unverifiedPoints(organ: OrganDetail, s: OrganSeries): UnverifiedPoint[] {
  const scans = new Map(organ.scans.map((sc) => [sc.record_id, sc]));
  return s.points
    .filter((p) => p.value !== null && scans.get(p.record_id)?.values[s.series_key]?.verified === false)
    .map((p) => ({ record_id: p.record_id, date: p.date }));
}

/** A comma-separated list that stops after `cap` items with "…". */
export function capList(items: string[], cap = 5): string {
  return items.length > cap ? `${items.slice(0, cap).join(", ")}, …` : items.join(", ");
}

/** Units that read better without a suffix ("TI-RADS 4", "nodules 2"). */
export const shownUnit = (u: string): string => (u === "count" || u === "score" ? "" : u);

/** Lowercase with ё folded to е, matching how the API matches organ aliases. */
const fold = (s: string) => s.toLowerCase().replaceAll("ё", "е");

/** Whether a line of a report mentions the organ by any of its aliases (stems such as "щитовидн"). */
export function mentions(line: string, aliases: string[]): boolean {
  const l = fold(line);
  return aliases.some((a) => a && l.includes(fold(a)));
}
