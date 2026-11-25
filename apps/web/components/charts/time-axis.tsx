import type { ClientI18n } from "@/lib/i18n/client-core";
import { isoDay, type TimeTick } from "./time-scale";

export type Plot = { left: number; right: number; top: number; bottom: number };

/** Vertical gridlines and the time labels under the plot; years are bold, months/days regular. */
export function TimeAxis({ ticks, x, plot, i18n }: { ticks: TimeTick[]; x: (ms: number) => number; plot: Plot; i18n: ClientI18n }) {
  const { formatDate } = i18n;
  return (
    <g aria-hidden="true">
      <line x1={plot.left} x2={plot.right} y1={plot.bottom} y2={plot.bottom} className="stroke-border" />
      {ticks.map((tick, i) => {
        const iso = isoDay(tick.ms);
        const label = tick.kind === "year" ? formatDate(iso, { year: "numeric" }) : tick.kind === "day" ? formatDate(iso, { day: "numeric", month: "short" })
          : i === 0 ? formatDate(iso, { month: "short", year: "numeric" }) : formatDate(iso, { month: "short" });
        const px = x(tick.ms);
        return (
          <g key={tick.ms}>
            <line x1={px} x2={px} y1={plot.top} y2={plot.bottom + 4} className={tick.kind === "year" ? "stroke-border" : "stroke-border/50"} strokeDasharray={tick.kind === "year" ? undefined : "2 4"} />
            <text x={px} y={plot.bottom + 18} textAnchor="middle" className={tick.kind === "year" ? "fill-foreground text-[11px] font-semibold" : "fill-muted-foreground text-[11px]"}>{label}</text>
          </g>
        );
      })}
    </g>
  );
}

/** Dashed "today" line with a small label; drawn only when today is inside the window. */
export function TodayMarker({ px, plot, label }: { px: number; plot: Plot; label: string }) {
  const anchor = px > plot.right - 40 ? "end" : "middle";
  return (
    <g aria-hidden="true">
      <line x1={px} x2={px} y1={plot.top} y2={plot.bottom} className="stroke-muted-foreground" strokeDasharray="4 3" strokeOpacity={0.7} />
      <text x={px} y={plot.top - 5} textAnchor={anchor} className="fill-muted-foreground text-[10px] font-medium uppercase tracking-wide">{label}</text>
    </g>
  );
}
