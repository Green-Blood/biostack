import type { ClientI18n } from "@/lib/i18n/client-core";
import type { HistoryPoint } from "@/lib/types";
import { durationLabel, ageDays } from "./duration";
import { dayMs } from "./time-scale";

type Run = { dir: "up" | "down" | "flat"; from: HistoryPoint; to: HistoryPoint };

/** A run is "flat" while its cumulative change stays under this many percent of its starting value. */
const FLAT_PCT = 3;

/** Change of `v` against `start`, in percent of |start| (a move away from zero counts as 100%). */
const pctFrom = (start: number, v: number): number => (start !== 0 ? ((v - start) / Math.abs(start)) * 100 : v === start ? 0 : Math.sign(v) * 100);

/**
 * Runs of movement, judged by cumulative change since the run's start (never step by step, so a slow steady
 * decline is not hidden as "flat"). A run is flat only while it stays within 3% of its starting value; once it
 * leaves that band it becomes a rise or a fall (from the run's start when the drift was one-way). A directional run continues while results keep moving the same way;
 * a move back starts a new run from the turning point.
 */
export function buildRuns(points: HistoryPoint[]): Run[] {
  if (points.length < 2) return [];
  const runs: Run[] = [{ dir: "flat", from: points[0], to: points[0] }];
  for (let i = 1; i < points.length; i++) {
    const b = points[i];
    let cur = runs[runs.length - 1];
    if (cur.dir !== "flat" && Math.sign(b.value - cur.to.value) !== (cur.dir === "up" ? 1 : -1)) {
      cur = { dir: "flat", from: cur.to, to: cur.to };
      runs.push(cur);
    }
    if (cur.dir !== "flat") { cur.to = b; continue; }
    const cum = pctFrom(cur.from.value, b.value);
    if (Math.abs(cum) < FLAT_PCT) { cur.to = b; continue; }
    const dir = cum > 0 ? "up" : "down";
    // A slow drift that was all one way (50 → 48.6 → 47.2) is one fall from its start, not "little change" plus a fall.
    const sign = cum > 0 ? 1 : -1;
    const drifted = points.slice(points.indexOf(cur.from), i + 1).every((p, k, arr) => k === 0 || Math.sign(p.value - arr[k - 1].value) !== -sign);
    if (cur.to === cur.from || drifted) { cur.dir = dir; cur.to = b; }
    else runs.push({ dir, from: cur.to, to: b });
  }
  return runs;
}

/**
 * Plain-language summary of a marker's history, written from the data (never by AI).
 * One point: just the point. Two: the pair, no trend. Three or more: the shape of the movement.
 */
export function buildCaption(i18n: ClientI18n, name: string, unitText: string, points: HistoryPoint[], todayMs: number): string {
  const { t, tp, formatDate, formatNumber } = i18n;
  const n = (v: number) => formatNumber(v, { maximumFractionDigits: 2 });
  const d = (iso: string) => formatDate(iso, { month: "short", year: "numeric" });
  const u = unitText ? ` ${unitText}` : "";
  if (!points.length) return "";
  const first = points[0], last = points[points.length - 1];
  const age = ageDays(dayMs(last.date), todayMs);
  const ageText = age === 0 ? t("charts.capLatestToday") : t("charts.capLatestAge", { duration: durationLabel(i18n, age) });
  let body: string;
  if (points.length === 1) {
    body = t("charts.capOne", { name, value: n(first.value), unit: u, date: formatDate(first.date) });
  } else if (points.length === 2) {
    body = t("charts.capTwo", { name, a: n(first.value), b: n(last.value), unit: u, d1: d(first.date), d2: d(last.date) });
  } else {
    const runs = buildRuns(points);
    if (runs.length <= 3) {
      const phrase = (r: Run, lead: boolean): string => {
        if (r.dir === "flat") return lead ? t("charts.capFlat", { value: n(r.from.value), unit: u }) : t("charts.capThenFlat");
        const key = r.dir === "up" ? (lead ? "charts.capRise" : "charts.capThenRise") : lead ? "charts.capFall" : "charts.capThenFall";
        return t(key, { a: n(r.from.value), b: n(r.to.value), unit: lead ? u : "" });
      };
      const head = runs[0];
      const lead = `${phrase(head, true)} ${t("charts.capBetween", { d1: d(head.from.date), d2: d(head.to.date) })}`;
      body = `${t("charts.capName", { name })} ${[lead, ...runs.slice(1).map((r) => phrase(r, false))].join(", ")}.`;
    } else {
      const values = points.map((p) => p.value);
      body = t("charts.capMany", { name, count: tp("charts.capResults", points.length), n: points.length, min: n(Math.min(...values)), max: n(Math.max(...values)), unit: u, latest: n(last.value), d1: d(first.date), d2: d(last.date) });
    }
  }
  return `${body} ${ageText}`;
}
