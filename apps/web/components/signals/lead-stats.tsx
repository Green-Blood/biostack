"use client";
import { useI18n } from "@/lib/i18n/client";
import type { ClientI18n } from "@/lib/i18n/client-core";
import type { SignalPosition, SignalSeries } from "@/lib/types";
import { metricText, type MetricKey } from "./metric-model";
import { PositionWords } from "./signal-tile";

export type LeadStat = {
  key: string; name: string; text: string | null; unit: string; date: string | null;
  position: SignalPosition | null; range: string | null; /** Shown under the value instead of a position, e.g. "average of 28 days". */
  sub?: string; href?: string; /** The value is a cut-off day (the export's last day, or today): no position. */ partial?: boolean;
};

/** A lead stat for the latest day of a series, with its usual range in the metric's display scale. */
export function leadOf(i18n: ClientI18n, key: MetricKey, s: SignalSeries | undefined, name?: string, unit?: string): LeadStat {
  const last = s?.points.at(-1) ?? null;
  const fmt = (v: number) => metricText(i18n.formatNumber, key, v);
  return {
    key, name: name ?? s?.name ?? key, unit: unit ?? s?.unit ?? "", text: last ? fmt(last.value) : null, date: last?.date ?? null,
    position: s?.position ?? null, href: `#chart-${key}`, partial: s?.partial ?? false,
    range: s?.band ? i18n.t("signals.usualRange", { lo: fmt(s.band.p25), hi: fmt(s.band.p75) }) : null,
  };
}

/** The plain numbers a page leads with: latest value, its date and where it sits against the owner's usual. */
export function LeadStats({ items, label }: { items: LeadStat[]; label: string }) {
  const { t, formatDate } = useI18n();
  return (
    <section aria-label={label}>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {items.map((s) => (
          <li key={s.key} className="surface relative flex min-w-0 flex-col gap-1.5 p-4 focus-within:ring-2 focus-within:ring-ring">
            <div className="flex items-baseline justify-between gap-2">
              {s.href ? (
                <a href={s.href} className="min-w-0 break-words hyphens-auto text-sm font-medium text-muted-foreground underline-offset-4 outline-none after:absolute after:inset-0 after:rounded-[inherit] hover:underline focus-visible:underline">{s.name}</a>
              ) : <span className="min-w-0 break-words hyphens-auto text-sm font-medium text-muted-foreground">{s.name}</span>}
              {s.date && <span className="shrink-0 text-xs text-muted-foreground tnum">{formatDate(s.date, { day: "numeric", month: "short" })}</span>}
            </div>
            {s.text !== null ? (
              <p className="tnum">
                <span className="text-2xl font-semibold tracking-tight sm:text-3xl">{s.text}</span>
                {s.unit && <span className="ml-1 text-sm text-muted-foreground">{s.unit}</span>}
              </p>
            ) : <p className="text-sm text-muted-foreground">{t("signals.noData")}</p>}
            <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1">
              {s.sub && <span className="text-xs text-muted-foreground">{s.sub}</span>}
              {s.position && <PositionWords position={s.position} />}
              {!s.sub && !s.position && s.text !== null && <span className="text-xs text-muted-foreground">{t(s.partial ? "signals.partialDay" : "signals.noBand")}</span>}
              {s.range && <span className="text-xs text-muted-foreground tnum">{s.range}</span>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
