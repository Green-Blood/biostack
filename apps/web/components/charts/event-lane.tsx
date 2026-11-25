import type { Context } from "@/lib/types";
import type { ClientI18n } from "@/lib/i18n/client-core";
import { DAY, dayMs, type Domain } from "./time-scale";
import type { Plot } from "./time-axis";

const LANE_H = 20;
const RECORD_ROW_H = 18;
const CHAR_W = 6.2;

type Course = { key: string; name: string; title: string; x1: number; x2: number; lane: number; labelInside: boolean };
type Marker = { key: string; x: number; kind: "visit" | "imaging"; title: string };

export type EventLayout = { height: number; courses: Course[]; markers: Marker[]; hasRecords: boolean };

/** Positions visits/imaging on one row and medication courses in non-overlapping lanes below it, all in the chart's pixel space. */
export function layoutEvents(context: Context | null, domain: Domain, x: (ms: number) => number, i18n: ClientI18n): EventLayout {
  const empty: EventLayout = { height: 0, courses: [], markers: [], hasRecords: false };
  if (!context) return empty;
  const { formatDate, t } = i18n;
  const markers: Marker[] = context.records
    .filter((r) => r.record_type !== "lab")
    .map((r) => ({ r, ms: dayMs(r.date) }))
    .filter(({ ms }) => ms >= domain[0] && ms <= domain[1])
    .map(({ r, ms }) => ({ key: `r${r.id}`, x: x(ms), kind: r.record_type === "imaging" ? ("imaging" as const) : ("visit" as const), title: `${formatDate(r.date)} · ${r.title}` }));
  const laneEnds: number[] = [];
  const courses: Course[] = [];
  const sorted = [...context.medications].sort((a, b) => a.start.localeCompare(b.start));
  for (const m of sorted) {
    const s = dayMs(m.start);
    const e = m.end ? dayMs(m.end) : s + 14 * DAY;
    if (e < domain[0] || s > domain[1]) continue;
    const x1 = x(Math.max(s, domain[0])), x2 = Math.max(x(Math.min(e, domain[1])), x1 + 6);
    const labelW = m.name.length * CHAR_W + 10;
    const labelInside = x2 - x1 >= labelW;
    const extent = labelInside ? x2 : x1 + labelW;
    let lane = laneEnds.findIndex((end) => end + 4 < x1);
    if (lane === -1) lane = laneEnds.push(extent) - 1;
    else laneEnds[lane] = extent;
    const period = m.end ? t("charts.coursePeriod", { start: formatDate(m.start), end: formatDate(m.end) }) : formatDate(m.start);
    courses.push({ key: m.name + m.start, name: m.name, title: `${m.name}${m.dosage ? `, ${m.dosage}` : ""}: ${period}`, x1, x2, lane, labelInside });
  }
  const hasRecords = markers.length > 0;
  const rows = (hasRecords ? RECORD_ROW_H : 0) + laneEnds.length * LANE_H;
  return { height: rows ? rows + 12 : 0, courses, markers, hasRecords };
}

export function EventLane({ layout, plot, top }: { layout: EventLayout; plot: Plot; top: number }) {
  if (!layout.height) return null;
  const courseTop = top + 8 + (layout.hasRecords ? RECORD_ROW_H : 0);
  return (
    <g>
      <line x1={plot.left} x2={plot.right} y1={top} y2={top} className="stroke-border" />
      {layout.markers.map((m) => (
        <g key={m.key} tabIndex={0} role="img" aria-label={m.title} className="outline-none [&:focus-visible>*]:stroke-foreground">
          <title>{m.title}</title>
          {m.kind === "imaging"
            ? <rect x={m.x - 4} y={top + 8} width={8} height={8} rx={1.5} style={{ fill: "var(--chart-3)" }} stroke="var(--card)" strokeWidth={1} />
            : <circle cx={m.x} cy={top + 12} r={4.5} style={{ fill: "var(--chart-5)" }} stroke="var(--card)" strokeWidth={1} />}
        </g>
      ))}
      {layout.courses.map((c) => {
        const flipLeft = !c.labelInside && c.x2 + 5 + c.name.length * CHAR_W > plot.right && c.x1 - 5 - c.name.length * CHAR_W >= plot.left;
        return (
          <g key={c.key} tabIndex={0} role="img" aria-label={c.title} className="outline-none [&:focus-visible>rect]:stroke-foreground">
            <title>{c.title}</title>
            <rect x={c.x1} y={courseTop + c.lane * LANE_H} width={c.x2 - c.x1} height={LANE_H - 4} rx={4} style={{ fill: "var(--chart-4)", stroke: "var(--chart-4)" }} fillOpacity={0.28} strokeWidth={1} />
            <text x={c.labelInside ? c.x1 + 5 : flipLeft ? c.x1 - 5 : c.x2 + 5} y={courseTop + c.lane * LANE_H + 11}
              textAnchor={flipLeft ? "end" : "start"} className="fill-foreground text-[10.5px]">{c.name}</text>
          </g>
        );
      })}
    </g>
  );
}

export function EventLegend({ i18n, show }: { i18n: ClientI18n; show: { visits: boolean; imaging: boolean; courses: boolean } }) {
  const { t } = i18n;
  if (!show.visits && !show.imaging && !show.courses) return null;
  return (
    <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label={t("charts.eventsLabel")}>
      {show.visits && <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: "var(--chart-5)" }} />{t("charts.legendVisit")}</li>}
      {show.imaging && <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-[2px]" style={{ background: "var(--chart-3)" }} />{t("charts.legendImaging")}</li>}
      {show.courses && <li className="flex items-center gap-1.5"><span className="h-2.5 w-5 rounded-[3px] border" style={{ background: "color-mix(in oklab, var(--chart-4) 28%, transparent)", borderColor: "var(--chart-4)" }} />{t("charts.legendCourse")}</li>}
    </ul>
  );
}
