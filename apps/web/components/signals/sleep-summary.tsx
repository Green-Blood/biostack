"use client";
import { DAY, dayMs, isoDay } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { ClientI18n } from "@/lib/i18n/client-core";
import type { SignalFreshness, SleepList, SleepNight } from "@/lib/types";
import { anchorOf, duration } from "./format";
import { clockIso, clockOf, clockSpread } from "./sleep-model";

type Item = { label: string; value: string; unit?: string; spoken: string; note: string };

const diffText = (i18n: ClientI18n, minutes: number): string => duration(i18n, Math.abs(minutes)).long;

/** How a 30-night average compares with the 30 nights before, in plain words; deliberately neutral. */
function changeNote(i18n: ClientI18n, diff: number | null, prev: number | null): string {
  const { t } = i18n;
  if (prev === null || diff === null) return t("signals.sumNoPrev");
  const p = `${duration(i18n, prev).short} ${t("signals.hoursUnit")}`;
  if (Math.abs(diff) < 1) return t("signals.sumSame", { prev: p });
  return t(diff > 0 ? "signals.sumMore" : "signals.sumLess", { diff: diffText(i18n, diff), prev: p });
}

function durationItem(i18n: ClientI18n, label: string, value: number | null, diff: number | null, prev: number | null): Item | null {
  if (value === null) return null;
  const d = duration(i18n, value);
  return { label, value: d.short, unit: i18n.t("signals.hoursUnit"), spoken: `${label}: ${d.long}`, note: changeNote(i18n, diff, prev) };
}

function clockItem(i18n: ClientI18n, label: string, values: number[]): Item | null {
  const s = clockSpread(values);
  if (!s) return null;
  const at = (m: number) => i18n.formatTime(clockIso(m));
  return { label, value: at(s.median), spoken: `${label}: ${at(s.median)}`, note: i18n.t("signals.sumSpread", { lo: at(s.p25), hi: at(s.p75) }) };
}

export function SleepSummary({ summary, nights, freshness }: { summary: SleepList["summary"]; nights: SleepNight[]; freshness: SignalFreshness }) {
  const i18n = useI18n();
  const { t, tp, formatDate } = i18n;
  const { last30, prev30, change } = summary;
  // The same 30-day window the API averages over: the anchor (today, or the data's last day when it is old) and the
  // 29 days before.
  const anchor = anchorOf(freshness);
  const since = isoDay(dayMs(anchor) - 29 * DAY);
  const recent = nights.filter((n) => n.wake_date >= since && n.wake_date <= anchor);
  const long = { day: "numeric", month: "long", year: "numeric" } as const;
  const title = freshness.stale ? t("signals.sumTitleTo", { date: formatDate(anchor, long) }) : t("signals.sumTitle");

  if (!last30.nights || !recent.length) {
    return (
      <section aria-labelledby="sum-h" className="space-y-2">
        <h2 id="sum-h" className="text-2xl font-semibold">{title}</h2>
        <p className="empty-state p-4 text-sm text-muted-foreground">{freshness.stale
          ? t("signals.sumNoRecentTo", { date: formatDate(anchor, long), night: formatDate(nights[0].wake_date, long) })
          : t("signals.sumNoRecent", { date: formatDate(nights[0].wake_date, long) })}</p>
      </section>
    );
  }
  const items = [
    durationItem(i18n, t("signals.sumAvgSleep"), last30.duration_min, change.duration_min, prev30.duration_min),
    durationItem(i18n, t("signals.sumDeep"), last30.deep, change.deep, prev30.deep),
    durationItem(i18n, t("signals.sumRem"), last30.rem, change.rem, prev30.rem),
    clockItem(i18n, t("signals.sumBedtime"), recent.map((n) => clockOf(n.start_local))),
    clockItem(i18n, t("signals.sumWake"), recent.map((n) => clockOf(n.end_local))),
  ].filter((x): x is Item => x !== null);

  return (
    <section aria-labelledby="sum-h" className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="sum-h" className="text-2xl font-semibold">{title}</h2>
        <span className="text-sm text-muted-foreground tnum">{tp("signals.sumRecorded", last30.nights)}</span>
      </div>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {items.map((it, i) => (
          <li key={it.label} className={i === 0 ? "surface col-span-2 flex min-w-0 flex-col gap-1 p-4 md:col-span-1" : "surface flex min-w-0 flex-col gap-1 p-4"}>
            <span className="text-sm font-medium text-muted-foreground">{it.label}</span>
            <p className="tnum" aria-label={it.spoken}>
              <span className="text-3xl font-semibold tracking-tight">{it.value}</span>
              {it.unit && <span className="ml-1.5 text-sm text-muted-foreground">{it.unit}</span>}
            </p>
            <span className="text-xs text-muted-foreground tnum">{it.note}</span>
          </li>
        ))}
      </ul>
      <p className="max-w-prose text-xs text-muted-foreground">{t("signals.sumNote")}</p>
    </section>
  );
}
