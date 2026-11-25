"use client";
import Link from "next/link";
import { ArrowRight, Moon } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import type { LastNight as Night } from "@/lib/types";
import { duration } from "./format";
import { STAGES } from "./sleep-model";

export function LastNightCard({ night }: { night: Night }) {
  const i18n = useI18n();
  const { t, formatDate, formatTime, formatNumber } = i18n;
  const total = duration(i18n, night.duration_min);
  // Stage minutes can overlap or fall short of the night's total, so the bar shows each as a share of their own sum.
  const staged = STAGES.reduce((sum, s) => sum + Math.max(0, night.stages[s.key]), 0);
  const parts = STAGES.map((s) => {
    const minutes = Math.max(0, night.stages[s.key]);
    const share = staged > 0 ? minutes / staged : 0;
    return { ...s, minutes, share, pct: formatNumber(share, { style: "percent", maximumFractionDigits: 0 }), time: duration(i18n, minutes) };
  });
  const list = parts.map((p) => t("signals.stageItem", { name: t(p.label), time: p.time.long, pct: p.pct })).join(", ");
  return (
    <article aria-labelledby="last-night-title" className="surface grid gap-5 p-5 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] md:gap-8">
      <div className="space-y-1">
        <h2 id="last-night-title" className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Moon className="size-4" aria-hidden />{t("signals.lastNightTitle")}
        </h2>
        <p className="tnum" aria-label={`${t("signals.asleepLabel")}: ${total.long}`}>
          <span className="text-5xl font-semibold tracking-tight">{total.short}</span>
          <span className="ml-1.5 text-base text-muted-foreground">{t("signals.hoursUnit")}</span>
        </p>
        <p className="text-sm text-muted-foreground tnum">
          {t("signals.inBed", { start: formatTime(night.start_local), end: formatTime(night.end_local) })}
        </p>
        <p className="text-sm text-muted-foreground">{t("signals.wokeUp", { date: formatDate(night.wake_date, { weekday: "long", day: "numeric", month: "long" }) })}</p>
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        {staged > 0 ? (
          <>
            <div role="img" aria-label={t("signals.stagesLabel", { list })} className="flex h-4 w-full overflow-hidden rounded-full bg-muted">
              {parts.filter((p) => p.share > 0).map((p, i) => (
                <span key={p.key} className="h-full" style={{ width: `${p.share * 100}%`, background: p.color, boxShadow: i ? "inset 2px 0 0 var(--card)" : undefined }} />
              ))}
            </div>
            <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4" aria-hidden>
              {parts.map((p) => (
                <li key={p.key} className="min-w-0 space-y-0.5">
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: p.color }} />{t(p.label)}
                  </span>
                  <span className="block text-sm tnum"><span className="font-medium">{p.time.short}</span> <span className="text-muted-foreground">· {p.pct}</span></span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">{t("signals.stagesNote")}</p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{t("signals.stagesNone")}</p>
        )}
        <Link href="/signals/sleep" className="mt-auto inline-flex items-center gap-1 self-start text-sm font-medium text-primary underline-offset-4 hover:underline">
          {t("signals.openSleep")}<ArrowRight className="size-4" aria-hidden />
        </Link>
      </div>
    </article>
  );
}
