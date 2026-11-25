"use client";
import { useMemo } from "react";
import { useI18n } from "@/lib/i18n/client";
import type { ScanColumn, ScanValue } from "@/lib/types";
import { shownUnit } from "./table-model";

const ARROW = { up: "▲", down: "▼", changed: "≠", same: "" } as const;

/** The previous value of each series per scan (`record_id|series_key`), across all scans, for "changed (was …)". */
export function usePrevText(scans: ScanColumn[]): Map<string, string | null> {
  const { formatNumber } = useI18n();
  return useMemo(() => {
    const last = new Map<string, string>(), out = new Map<string, string | null>();
    for (const s of scans) for (const [k, v] of Object.entries(s.values)) {
      out.set(`${s.record_id}|${k}`, last.get(k) ?? null);
      last.set(k, v.value !== null ? formatNumber(v.value, { maximumFractionDigits: 2 }) : (v.value_text ?? ""));
    }
    return out;
  }, [scans, formatNumber]);
}

/** One table cell: the value with its unit, a neutral tint and arrow when it moved, italics and "?" when unverified. */
export function ScanCell({ v, prevText, className = "", staticMode = false }: { v: ScanValue | undefined; prevText: string | null; className?: string; staticMode?: boolean }) {
  const { t, formatNumber, unit } = useI18n();
  if (!v) return <td className={`px-3 py-2 text-center text-muted-foreground/50 ${className}`}><span aria-hidden>·</span><span className="sr-only">—</span></td>;
  const num = (n: number, d = 2) => formatNumber(n, { maximumFractionDigits: d });
  const dir = v.change?.direction ?? "same";
  const moved = dir !== "same";
  const u = unit(shownUnit(v.unit));
  const text = v.value !== null ? num(v.value) : (v.value_text ?? "");
  const delta = v.change?.delta ?? null;
  const deltaText = delta !== null && delta !== 0
    ? `${delta > 0 ? "+" : "−"}${num(Math.abs(delta))}${v.change?.pct != null ? ` · ${num(Math.abs(v.change.pct), 1)}%` : ""}`
    : null;
  const changeTitle = !moved ? "" : dir === "changed"
    ? t("organs.changeText", { prev: prevText ?? "—" })
    : deltaText ? t("organs.changeBy", { delta: `${delta! > 0 ? "+" : "−"}${num(Math.abs(delta!))} ${u}`.trim() }) : t(dir === "up" ? "organs.cellUp" : "organs.cellDown");
  const unverified = v.verified ? "" : t(v.origin === "ai" ? "organs.unverifiedAi" : v.origin === "rule" ? "organs.unverifiedRule" : "organs.unverifiedManual");
  const title = [changeTitle, unverified].filter(Boolean).join("\n");
  return (
    <td title={staticMode ? undefined : title || undefined} className={`px-3 py-2 align-top tnum ${moved ? "bg-chart-4/15" : ""} ${className}`}>
      <div className={`flex items-baseline justify-end gap-1 whitespace-nowrap ${v.verified ? "" : "italic"}`}>
        {moved && <span aria-hidden className="text-[10px] not-italic text-foreground/70">{ARROW[dir]}</span>}
        <span className={v.value === null ? "max-w-[9rem] whitespace-normal text-right text-[13px] leading-tight" : "font-medium"}>{text}</span>
        {u && v.value !== null && <span className="text-xs text-muted-foreground">{u}</span>}
        {!v.verified && <span aria-hidden className="text-xs font-semibold not-italic text-muted-foreground">?</span>}
      </div>
      {deltaText && <div className="mt-0.5 text-right text-[11px] leading-none text-muted-foreground">{deltaText}</div>}
      {/* Static (doctor/print) mode has no hover: what a changed text value was before is printed under it. */}
      {staticMode && dir === "changed" && prevText && <div className="mt-0.5 max-w-[9rem] text-right text-xs leading-tight text-muted-foreground">{t("organs.doctorWas", { prev: prevText })}</div>}
      {title && <span className="sr-only">{title}</span>}
    </td>
  );
}
