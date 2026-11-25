import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { MarkerSummaryFull } from "@/lib/types";
import { buttonVariants } from "@/components/ui/button";
import { getI18n } from "@/lib/i18n/server";
import { MarkersView } from "@/components/biomarkers/markers-view";
import { UnmappedPanel, type UnmappedItem } from "@/components/biomarkers/unmapped-panel";

export default async function BiomarkersPage() {
  const { t } = await getI18n();
  const [markers, unmapped] = await Promise.all([
    apiGet<MarkerSummaryFull[]>("biomarkers"),
    apiGet<UnmappedItem[]>("review/unmapped"),
  ]);
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold">{t("biomarkers.title")}</h1>
          <p className="mt-2 max-w-prose text-muted-foreground">{t("biomarkers.intro")}</p>
        </div>
        <Link href="/labs/new" className={buttonVariants()}>{t("biomarkers.addResults")}</Link>
      </header>
      <UnmappedPanel items={unmapped} />
      {markers.length === 0
        ? <p className="rounded-xl border border-dashed p-8 text-center text-muted-foreground">{t("biomarkers.noResults")}</p>
        : <MarkersView markers={markers} />}
    </div>
  );
}
