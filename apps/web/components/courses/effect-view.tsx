"use client";
import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Hourglass, Minus } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import { getJson } from "@/lib/request";
import type { CourseEffect } from "@/lib/types";

/** Before/after result of one course for one marker, with the API's own caveat. Loads itself; shows honest loading and error states. */
export function EffectView({ courseId, markerKey, refreshKey = 0 }: { courseId: number; markerKey: string; refreshKey?: number }) {
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const [effect, setEffect] = useState<CourseEffect | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    getJson<CourseEffect>(`courses/${courseId}/effect?marker=${encodeURIComponent(markerKey)}`)
      .then((e) => { if (live) { setEffect(e); setFailed(false); } })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [courseId, markerKey, refreshKey]);

  if (failed) return <p role="alert" className="text-sm text-muted-foreground">{t("courses.effFailed")}</p>;
  if (!effect) return <p className="text-sm text-muted-foreground" aria-busy="true">{t("courses.effLoading")}</p>;

  const num = (n: number) => formatNumber(n, { maximumFractionDigits: 4 });
  const sign = (n: number) => (n > 0 ? "+" : n < 0 ? "−" : "");
  const u = unit(effect.unit);
  const caveat = effect.note ? <p className="mt-2 text-xs text-muted-foreground">{effect.note}</p> : null;

  if (effect.state === "waiting_for_retest") {
    return (
      <div>
        <p className="flex items-start gap-2 text-sm"><Hourglass className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
          <span>{effect.retest_due_date ? t("courses.effWaiting", { date: formatDate(effect.retest_due_date) }) : t("courses.effWaitingNoDate")}</span></p>
        {caveat}
      </div>
    );
  }
  if (effect.state === "unit_mismatch" && effect.before && effect.after) {
    const ub = unit(effect.before?.unit ?? effect.unit), ua = unit(effect.after?.unit ?? effect.unit);
    return (
      <div>
        <p className="tnum text-base font-medium">
          <span className="sr-only">{t("courses.effBeforeAfter")}: </span>{num(effect.before.value)} <span className="font-normal text-muted-foreground">{ub}</span> → {num(effect.after.value)} <span className="font-normal text-muted-foreground">{ua}</span>
        </p>
        <p className="tnum text-xs text-muted-foreground">{formatDate(effect.before.date)} → {formatDate(effect.after.date)}</p>
        <p className="mt-1.5 flex items-start gap-2 text-sm text-warn"><Minus className="mt-0.5 size-4 shrink-0" aria-hidden /><span>{t("courses.effUnitMismatch")}</span></p>
        {caveat}
      </div>
    );
  }
  if (effect.state === "no_baseline" || effect.state === "unit_mismatch" || !effect.before || !effect.after) {
    return (
      <div>
        <p className="flex items-start gap-2 text-sm text-muted-foreground"><Minus className="mt-0.5 size-4 shrink-0" aria-hidden /><span>{t("courses.effNoBaseline")}</span></p>
        {caveat}
      </div>
    );
  }
  const abs = effect.delta_abs, pct = effect.delta_pct;
  const change = abs === null ? null : `${sign(abs)}${formatNumber(Math.abs(abs), { maximumFractionDigits: 2 })} ${u}${pct === null ? "" : ` (${sign(pct)}${formatNumber(Math.abs(pct), { maximumFractionDigits: 1 })}%)`}`;
  const up = (abs ?? 0) >= 0;
  const Arrow = up ? ArrowUpRight : ArrowDownRight;
  return (
    <div>
      <p className="tnum text-base font-medium">
        <span className="sr-only">{t("courses.effBeforeAfter")}: </span>{num(effect.before.value)} → {num(effect.after.value)} <span className="font-normal text-muted-foreground">{u}</span>
      </p>
      <p className="tnum text-xs text-muted-foreground">{formatDate(effect.before.date)} → {formatDate(effect.after.date)}{effect.days_between !== null && <> · {tp("courses.effDaysBetween", effect.days_between)}</>}</p>
      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {change && <span className="tnum inline-flex items-center gap-1"><Arrow className="size-4" aria-hidden />{t("courses.effChange", { change })}</span>}
        {effect.toward_range === null
          ? effect.stayed_in_range === true
            ? <span className="font-medium">{t("courses.effStayed")}</span>
            : <span className="text-muted-foreground">{t("courses.effNoRange")}</span>
          : effect.toward_range
            ? <span className="font-medium text-ok">▲ {t("courses.effToward")}</span>
            : <span className="font-medium text-warn">▼ {t("courses.effAway")}</span>}
      </p>
      {caveat}
    </div>
  );
}
