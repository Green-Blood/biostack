"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "cn";
import { useI18n } from "@/lib/i18n/client";
import type { OrganDetail } from "@/lib/types";
import { ScanCell, usePrevText } from "./scan-cell";
import { defaultWindow, rowGroups, WINDOW_THRESHOLD, windowScans, yearGroups, type Param, type WindowKind } from "./table-model";

const WINDOWS: { kind: WindowKind; key: "organs.windowLast5" | "organs.windowLastYear" | "organs.windowAll" }[] = [
  { kind: "last5", key: "organs.windowLast5" },
  { kind: "lastYear", key: "organs.windowLastYear" },
  { kind: "all", key: "organs.windowAll" },
];
// Fixed width so the year labels can stick just to its right while the columns scroll.
const STICKY = "sticky left-0 z-10 w-40 min-w-40 max-w-40 bg-card shadow-[1px_0_0_var(--border)] sm:w-48 sm:min-w-48 sm:max-w-48";

/** The row header text: the parameter name on a group's first row, the side ("left"/"right") under it or indented. */
export function ParamLabel({ p, first }: { p: Param; first: boolean }) {
  const { t } = useI18n();
  return (
    <>
      {first && <span className="block leading-snug">{p.name}</span>}
      {p.side && <span className={cn("block text-xs text-muted-foreground", first ? "mt-0.5" : "pl-3")}>{t(p.side === "left" ? "organs.sideLeft" : "organs.sideRight")}</span>}
    </>
  );
}

/** Parameters as rows, scans as columns (oldest → newest), the newest end scrolled into view. */
export function ScanTable({ organ, onOpenScan }: { organ: OrganDetail; onOpenScan: (recordId: number) => void }) {
  const { t, formatDate } = useI18n();
  const [win, setWin] = useState<WindowKind>(() => defaultWindow(organ.scans.length));
  const scans = useMemo(() => windowScans(organ.scans, win), [organ.scans, win]);
  const years = useMemo(() => yearGroups(scans), [scans]);
  const groups = useMemo(() => rowGroups(organ.params), [organ.params]);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => { const el = scroller.current; if (el) el.scrollLeft = el.scrollWidth; }, [scans]);

  // The previous value of each series, across all scans (not only the shown ones), for "changed (was …)".
  const prevText = usePrevText(organ.scans);

  return (
    <div className="space-y-3">
      {organ.scans.length > WINDOW_THRESHOLD && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div role="radiogroup" aria-label={t("organs.windowLabel")} className="inline-flex rounded-2xl bg-muted p-[3px] text-sm">
            {WINDOWS.map(({ kind, key }) => (
              <button key={kind} type="button" role="radio" aria-checked={win === kind} onClick={() => setWin(kind)}
                className={cn("h-7 rounded-xl px-3 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
                  win === kind ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>
                {t(key)}
              </button>
            ))}
          </div>
          <span className="text-xs text-muted-foreground tnum" aria-live="polite">{t("organs.windowShowing", { n: scans.length, total: organ.scans.length })}</span>
        </div>
      )}
      <div ref={scroller} className="surface relative w-fit max-w-full overflow-x-auto overscroll-x-contain" role="region" tabIndex={0} aria-label={t("organs.tableTitle")}>
        <table className="w-max border-separate border-spacing-0 text-sm">
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" rowSpan={2} className={cn(STICKY, "z-20 border-b px-3 py-2 text-left align-bottom font-medium")}>{t("organs.colParam")}</th>
              {years.map((y, i) => (
                <th key={`${y.year}-${i}`} scope="colgroup" colSpan={y.span} className="border-b border-l px-3 pt-2 pb-1 text-left font-semibold tracking-wide text-foreground/80 tnum">
                  <span className="sticky left-[10.75rem] sm:left-[12.75rem]">{y.year ?? t("organs.noDate")}</span>
                </th>
              ))}
            </tr>
            <tr>
              {scans.map((s) => {
                const label = s.date ? formatDate(s.date, { day: "numeric", month: "short" }) : t("organs.noDate");
                return (
                  <th key={s.record_id} scope="col" className="border-b px-1 py-1 text-right font-medium">
                    <button type="button" onClick={() => onOpenScan(s.record_id)}
                      aria-label={t("organs.openConclusion", { date: s.date ? formatDate(s.date) : t("organs.noDate") })}
                      title={s.date_suspect ? t("organs.dateUnconfirmed") : s.title}
                      className="whitespace-nowrap rounded-lg px-2 py-1 text-primary underline-offset-4 outline-none tnum hover:bg-muted hover:underline focus-visible:ring-2 focus-visible:ring-ring">
                      {label}{s.date_suspect && <span aria-hidden className="ml-0.5 text-warn">?</span>}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => g.rows.map((p, k) => {
              const last = k === g.rows.length - 1;
              return (
                <tr key={p.series_key} className="group">
                  <th scope="row" className={cn(STICKY, "px-3 py-2 text-left align-top font-normal group-hover:bg-muted", last && "border-b")}>
                    <ParamLabel p={p} first={k === 0} />
                  </th>
                  {scans.map((s) => (
                    <ScanCell key={s.record_id} v={s.values[p.series_key]} prevText={prevText.get(`${s.record_id}|${p.series_key}`) ?? null} className={last ? "border-b" : ""} />
                  ))}
                </tr>
              );
            }))}
          </tbody>
        </table>
      </div>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span><span className="rounded bg-chart-4/15 px-1">{t("organs.legendChange")}</span></span>
        <span className="italic">{t("organs.legendUnverified")}</span>
      </p>
    </div>
  );
}

