"use client";
import { useI18n } from "@/lib/i18n/client";
import type { BodyKind, BodyMeasurement, BodySnapshot } from "@/lib/types";
import { cn } from "cn";
import { COMPOSITION, snapshotOf } from "./body-kinds";
import { Sparkline } from "./sparkline";

type Props = { body: BodySnapshot | null; rows: BodyMeasurement[]; bodyFailed: boolean; selected: BodyKind | null; onSelect: (k: BodyKind) => void };

export function CompositionCards({ body, rows, bodyFailed, selected, onSelect }: Props) {
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const snap = snapshotOf(body, rows);
  const cards = COMPOSITION.filter((m) => snap.latest[m.kind]);
  if (!cards.length) {
    return bodyFailed && !rows.length
      ? <p role="alert" className="empty-state p-5 text-outrange">{t("profile.compLoadFailed")}</p>
      : <p className="empty-state p-5 text-muted-foreground">{t("profile.compNone")}</p>;
  }
  return (
    <div className="space-y-3">
      <p className="max-w-prose text-sm text-muted-foreground">{t("profile.compIntro")}</p>
      {bodyFailed && <p role="alert" className="text-sm text-outrange">{t("profile.compLoadFailed")}</p>}
      <ul className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((m) => {
          const last = snap.latest[m.kind]!, prev = snap.previous[m.kind];
          const n = (v: number) => formatNumber(v, { maximumFractionDigits: m.digits });
          const u = unit(m.unit);
          const label = t(m.label);
          const series = rows.filter((r) => r.kind === m.kind).sort((a, b) => a.date.localeCompare(b.date));
          const delta = prev ? Math.round((last.value - prev.value) * 10 ** m.digits) / 10 ** m.digits : null;
          const on = selected === m.kind;
          return (
            <li key={m.kind} className="min-w-0">
              <button type="button" aria-pressed={on} aria-label={`${t("profile.compSelect", { kind: label })}. ${n(last.value)} ${u}`} onClick={() => onSelect(m.kind)}
                className={cn("surface surface-interactive flex h-full w-full min-w-0 flex-col gap-1.5 p-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 motion-reduce:transition-none", on && "border-primary ring-2 ring-primary/40")}>
                <span className="eyebrow">{label}</span>
                <span className="font-heading text-3xl font-semibold tnum">{n(last.value)} <span className="text-base font-normal text-muted-foreground">{u}</span></span>
                <span className="text-xs text-muted-foreground tnum">{t("profile.compLatestOn", { date: formatDate(last.date) })}</span>
                <span className="text-sm tnum">
                  {prev && delta !== null
                    ? delta === 0
                      ? t("profile.compUnchanged", { date: formatDate(prev.date) })
                      : t("profile.compChanged", { arrow: delta > 0 ? "▲" : "▼", delta: `${delta > 0 ? "+" : "−"}${n(Math.abs(delta))}`, unit: u, date: formatDate(prev.date) })
                    : <span className="text-muted-foreground">{t("profile.compNoPrev")}</span>}
                </span>
                <span className="mt-auto pt-1">
                  {series.length >= 3
                    ? <Sparkline points={series.slice(-30)} label={t("profile.compSpark", { kind: label, n: Math.min(series.length, 30) })} />
                    : <span className="text-xs text-muted-foreground">{tp("profile.compTooFew", series.length || 1)}</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
