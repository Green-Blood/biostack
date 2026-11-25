"use client";
import type { ReactNode } from "react";
import { buildCaption } from "@/components/charts/caption";
import { TimeChart, type ChartPoint } from "@/components/charts/time-chart";
import type { Domain } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { Context } from "@/lib/types";
import { pointsIn } from "./metric-model";

type Props = {
  id: string; title: string; unit: string; points: ChartPoint[]; context: Context | null; domain: Domain; todayMs: number;
  /** A control beside the title (e.g. the SDNN/RMSSD switch). */
  action?: ReactNode;
  /** One quiet line under the caption: how the value is worked out, or what else the tooltip shows. */
  note?: string;
};

/** One daily metric: title, a plain caption of the visible period, the shared time chart with the usual band and events. */
export function MetricChart({ id, title, unit, points, context, domain, todayMs, action, note }: Props) {
  const i18n = useI18n();
  const shown = pointsIn(points, domain);
  return (
    <article id={id} aria-labelledby={`${id}-h`} className="surface min-w-0 scroll-mt-24 space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <h3 id={`${id}-h`} className="font-sans text-base font-semibold leading-snug">
          {title}{unit && <span className="ml-1.5 text-sm font-normal text-muted-foreground">{unit}</span>}
        </h3>
        {action}
      </div>
      <p className="text-sm text-muted-foreground">
        {shown.length >= 3 ? buildCaption(i18n, title, unit, shown, todayMs) : i18n.t("heart.tooLittle")}
      </p>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      <TimeChart name={title} unit={unit} points={points} tiers={[]} context={context} domain={domain} todayMs={todayMs} band="usual" />
    </article>
  );
}
