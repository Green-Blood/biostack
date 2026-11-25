"use client";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/client";
import type { OrganIndex } from "@/lib/types";
import { OrganCard } from "./organ-card";

export function OrgansIndex({ data }: { data: OrganIndex }) {
  const { t, formatDate } = useI18n();
  if (data.organs.length === 0 && data.unassigned.length === 0)
    return <p className="rounded-xl border border-dashed p-8 text-center text-muted-foreground">{t("organs.empty")}</p>;
  return (
    <div className="space-y-8">
      {data.organs.length > 0 && (
        <>
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.organs.map((o) => <OrganCard key={o.key} organ={o} />)}
          </ul>
          <p className="max-w-prose text-xs text-muted-foreground">{t("organs.measurementsVary")}</p>
        </>
      )}
      {data.unassigned.length > 0 && (
        <section aria-labelledby="unassigned-title" className="space-y-3">
          <div>
            <h2 id="unassigned-title" className="text-xl font-semibold">{t("organs.unassignedTitle")}</h2>
            <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t("organs.unassignedHint")}</p>
          </div>
          <ul className="surface divide-y divide-border rounded-2xl border border-border">
            {data.unassigned.map((r) => (
              <li key={r.record_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3">
                <Link href={`/records/${r.record_id}`} className="min-w-0 break-words font-medium underline-offset-4 hover:underline">{r.title}</Link>
                <span className="flex items-center gap-3 text-sm text-muted-foreground tnum">
                  {r.date ? formatDate(r.date) : t("organs.noDate")}
                  <Link href={`/records/${r.record_id}`} className="text-primary underline-offset-4 hover:underline">{t("organs.tagIt")}</Link>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
