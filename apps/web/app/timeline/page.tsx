import { redirect } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { RecordItem } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { AddVisitButton } from "@/components/records/add-visit-button";
import { TimelineView } from "@/components/timeline/timeline-view";

export default async function TimelinePage({ searchParams }: PageProps<"/timeline">) {
  const { record } = await searchParams;
  // Old deep links (?record=<id>) now open the record's own page.
  const linked = typeof record === "string" && /^\d+$/.test(record) ? record : null;
  if (linked) redirect(`/records/${linked}`);
  const { t } = await getI18n();
  const records = await apiGet<RecordItem[]>("records");
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-semibold">{t("timeline.title")}</h1>
          <p className="mt-2 max-w-prose text-muted-foreground">{t("timeline.intro")}</p>
        </div>
        <AddVisitButton label={t("records.addVisit")} />
      </header>
      <TimelineView records={records} />
    </div>
  );
}
