"use client";
import { useState } from "react";
import { Dumbbell } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import type { WorkoutItem, WorkoutType } from "@/lib/types";
import { duration } from "./format";

const PAGE = 20;

function Chip({ selected, onClick, label, count }: { selected: boolean; onClick: () => void; label: string; count: number }) {
  const { formatNumber } = useI18n();
  return (
    <button type="button" aria-pressed={selected} onClick={onClick}
      className={cn("inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border px-3 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
        selected ? "border-foreground/40 bg-foreground text-background" : "border-border bg-card text-foreground hover:bg-muted")}>
      <span className="truncate">{label}</span>
      <span className={cn("tnum text-xs", selected ? "text-background/80" : "text-muted-foreground")}>{formatNumber(count)}</span>
    </button>
  );
}

type Props = { items: WorkoutItem[]; total: number; types: WorkoutType[]; type: number | null; onType: (code: number | null) => void };

/** Workouts in the period, newest first, with a type filter whose chips count the period's workouts. */
export function WorkoutsList({ items, total, types, type, onType }: Props) {
  const i18n = useI18n();
  const { t, formatDate, formatTime, formatNumber } = i18n;
  const [shown, setShown] = useState(PAGE);
  const pick = (code: number | null) => { onType(code); setShown(PAGE); };
  return (
    <div className="space-y-3">
      <div role="group" aria-label={t("activity.filterLabel")} className="flex flex-wrap gap-2">
        <Chip selected={type === null} onClick={() => pick(null)} label={t("activity.filterAll")} count={total} />
        {types.map((ty) => <Chip key={ty.type_code} selected={type === ty.type_code} onClick={() => pick(ty.type_code)} label={ty.type_name} count={ty.count} />)}
      </div>
      {items.length === 0 ? (
        <p className="empty-state p-4 text-sm text-muted-foreground">{t("activity.workoutsNone")}</p>
      ) : (
        <ul className="surface divide-y overflow-hidden">
          {items.slice(0, shown).map((w) => (
            <li key={w.id} className="flex items-start gap-3 px-4 py-3">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Dumbbell className="size-4" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="min-w-0 break-words font-medium">{w.type_name}</span>
                  <span className="shrink-0 text-sm text-muted-foreground tnum">
                    {formatDate(w.local_date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}, {formatTime(w.start_local)}
                  </span>
                </div>
                <p className="mt-0.5 flex flex-wrap gap-x-3 text-sm text-muted-foreground tnum">
                  <span>{duration(i18n, w.duration_min).long}</span>
                  {w.distance_m ? <span>{t("activity.km", { n: formatNumber(w.distance_m / 1000, { maximumFractionDigits: 2 }) })}</span> : null}
                  {w.kcal ? <span>{t("activity.kcal", { n: formatNumber(w.kcal, { maximumFractionDigits: 0 }) })}</span> : null}
                  {w.hr_avg ? <span>{t(w.hr_max ? "activity.hrAvgMax" : "activity.hrAvg", { avg: formatNumber(w.hr_avg, { maximumFractionDigits: 0 }), max: formatNumber(w.hr_max ?? 0, { maximumFractionDigits: 0 }) })}</span> : null}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {items.length > shown && (
        <Button variant="outline" onClick={() => setShown((n) => n + PAGE)}>
          {t("activity.showMore", { n: Math.min(PAGE, items.length - shown), left: formatNumber(items.length - shown) })}
        </Button>
      )}
    </div>
  );
}
