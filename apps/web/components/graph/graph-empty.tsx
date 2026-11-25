"use client";
import { useI18n } from "@/lib/i18n/client";

export function GraphEmpty({ notes, biomarkerCount }: { notes: string[]; biomarkerCount: number }) {
  const { t } = useI18n();
  return (
    <section aria-labelledby="empty-h" className="rounded-2xl border border-dashed p-6">
      <h2 id="empty-h">{t("graph.emptyTitle")}</h2>
      {notes.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      <p className="mt-4 max-w-prose text-muted-foreground">
        {t("graph.emptyText")}
        {biomarkerCount > 0 && ` ${t("graph.emptyLabs")}`}
      </p>
    </section>
  );
}
