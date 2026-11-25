"use client";
import { useI18n } from "@/lib/i18n/client";
import { cn } from "cn";
import type { Period, PeriodKind } from "./period";

const KINDS: { kind: PeriodKind; key: "charts.period3m" | "charts.period1y" | "charts.periodAll" | "charts.periodCustom" }[] = [
  { kind: "3m", key: "charts.period3m" },
  { kind: "1y", key: "charts.period1y" },
  { kind: "all", key: "charts.periodAll" },
  { kind: "custom", key: "charts.periodCustom" },
];

/** The one period control, identical above every time chart. */
export function PeriodSelector({ value, onChange, minDate, maxDate }: { value: Period; onChange: (p: Period) => void; minDate?: string; maxDate?: string }) {
  const { t } = useI18n();
  const pick = (kind: PeriodKind) => onChange({ ...value, kind });
  const invalid = value.kind === "custom" && value.from !== "" && value.to !== "" && value.to <= value.from;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div role="radiogroup" aria-label={t("charts.periodLabel")} className="inline-flex rounded-2xl bg-muted p-[3px] text-sm">
        {KINDS.map(({ kind, key }) => (
          <button key={kind} type="button" role="radio" aria-checked={value.kind === kind} onClick={() => pick(kind)}
            className={cn("h-7 rounded-xl px-3 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
              value.kind === kind ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>
            {t(key)}
          </button>
        ))}
      </div>
      {value.kind === "custom" && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-1.5 text-muted-foreground">{t("charts.dateFrom")}
            <input type="date" value={value.from} min={minDate} max={value.to || maxDate} onChange={(e) => onChange({ ...value, from: e.target.value })} className="h-8 rounded-xl border bg-card px-2 text-foreground tnum" />
          </label>
          <label className="flex items-center gap-1.5 text-muted-foreground">{t("charts.dateTo")}
            <input type="date" value={value.to} min={value.from || minDate} max={maxDate} onChange={(e) => onChange({ ...value, to: e.target.value })} className="h-8 rounded-xl border bg-card px-2 text-foreground tnum" />
          </label>
          {invalid && <span role="alert" className="text-outrange">{t("charts.customInvalid")}</span>}
        </div>
      )}
    </div>
  );
}
