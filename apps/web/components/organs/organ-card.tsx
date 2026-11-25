"use client";
import Link from "next/link";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import type { OrganSummary } from "@/lib/types";

function HeadlineChange({ h }: { h: NonNullable<OrganSummary["headline"]> }) {
  const { t, formatNumber } = useI18n();
  if (h.previous === null || h.delta === null) return <span className="text-xs text-muted-foreground">{t("organs.tooLittleData")}</span>;
  const pct = h.pct === null ? "" : `${formatNumber(Math.abs(h.pct), { maximumFractionDigits: 1 })}%`;
  const words = h.delta === 0 ? t("organs.changeSame") : t(h.delta > 0 ? "organs.changeUp" : "organs.changeDown", { pct: pct || "—" });
  const Icon = h.delta > 0 ? ArrowUp : h.delta < 0 ? ArrowDown : Minus;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground tnum" title={t("organs.changeSince", { pct: words })} aria-label={t("organs.changeSince", { pct: words })}>
      <Icon className="size-3.5" aria-hidden />{pct}
    </span>
  );
}

export function OrganCard({ organ }: { organ: OrganSummary }) {
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const h = organ.headline;
  return (
    <li className="surface group relative flex flex-col gap-2 rounded-2xl border border-border bg-card p-3.5 shadow-card transition-shadow focus-within:ring-2 focus-within:ring-ring hover:shadow-md motion-reduce:transition-none">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/organs/${encodeURIComponent(organ.key)}`} aria-label={t("organs.openOrgan", { name: organ.name })}
          className="min-w-0 break-words text-lg font-medium leading-snug underline-offset-4 outline-none after:absolute after:inset-0 after:rounded-2xl hover:underline focus-visible:underline">
          {organ.name}
        </Link>
        {organ.unverified_count > 0 && (
          <span className="shrink-0 rounded-full border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground tnum">{t("organs.unverified", { n: organ.unverified_count })}</span>
        )}
      </div>
      {h ? (
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 tnum">
          <span className="min-w-0 text-sm text-muted-foreground">{h.name}</span>
          <span className="flex items-baseline gap-2">
            <span className="text-lg"><span className="font-semibold">{formatNumber(h.value, { maximumFractionDigits: 4 })}</span> <span className="text-muted-foreground">{unit(h.unit)}</span></span>
            <HeadlineChange h={h} />
          </span>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t("organs.tooLittleData")}</p>
      )}
      <div className="mt-auto flex flex-wrap items-baseline justify-between gap-x-3 pt-1 text-xs text-muted-foreground tnum">
        <span>{tp("organs.scans", organ.scan_count)}</span>
        <span>{t("organs.latest", { date: organ.latest_date ? formatDate(organ.latest_date) : t("organs.noDate") })}</span>
      </div>
    </li>
  );
}
