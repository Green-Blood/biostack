"use client";
import { useState } from "react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/client";
import type { MarkerSummaryFull } from "@/lib/types";
import { MarkerValue } from "./marker-card";
import { describePosition, positionOf } from "./status";

const LIMIT = 8;

/** Markers whose latest result is out of range, the furthest outside first. */
export function AttentionStrip({ markers }: { markers: MarkerSummaryFull[] }) {
  const i18n = useI18n();
  const { t, tp } = i18n;
  const [all, setAll] = useState(false);
  if (markers.length === 0) return <p className="rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground">{t("biomarkers.attentionNone")}</p>;
  const shown = all ? markers : markers.slice(0, LIMIT);
  return (
    <section aria-labelledby="attention-title" className="rounded-2xl border border-border bg-card p-4 shadow-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="attention-title" className="text-lg font-semibold">{t("biomarkers.attentionTitle")}</h2>
        <p className="text-sm text-muted-foreground">{tp("biomarkers.attentionCount", markers.length)}</p>
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map((m) => (
          <li key={m.marker_key}>
            <Link href={`/biomarkers/${encodeURIComponent(m.marker_key)}`} className="block h-full rounded-xl border border-border px-3 py-2 text-sm outline-none transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none">
              <span className="block truncate font-medium">{m.display_name}</span>
              <span className="tnum"><MarkerValue m={m} /></span>
              <span className="block text-xs text-outrange">{describePosition(i18n, positionOf(m))}</span>
            </Link>
          </li>
        ))}
      </ul>
      {markers.length > LIMIT && (
        <button type="button" onClick={() => setAll(!all)} className="mt-3 rounded text-sm underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {all ? t("biomarkers.attentionLess") : t("biomarkers.attentionMore", { n: markers.length })}
        </button>
      )}
    </section>
  );
}
