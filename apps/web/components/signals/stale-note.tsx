"use client";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/client";
import type { SignalFreshness } from "@/lib/types";
import { IMPORT_HREF } from "./format";

/** One neutral line when the watch data is old (there is no automatic sync yet): how far it reaches and where to get
 *  newer data. Renders nothing while the data is current. */
export function StaleNote({ freshness, className }: { freshness: SignalFreshness; className?: string }) {
  const { t, formatDate } = useI18n();
  if (!freshness.stale || !freshness.as_of) return null;
  return (
    <p className={`text-sm text-muted-foreground ${className ?? ""}`}>
      <span className="tnum">{t("signals.staleNote", { date: formatDate(freshness.as_of, { day: "numeric", month: "long", year: "numeric" }) })}</span>
      {" · "}
      <Link href={IMPORT_HREF} className="font-medium text-primary underline-offset-4 hover:underline">{t("signals.staleAction")}</Link>
    </p>
  );
}
