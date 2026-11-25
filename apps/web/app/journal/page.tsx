import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { BedtimeReadout, CnsTest, JournalEntry, Preset, SupplementLog } from "@/lib/types";
import { TapTest } from "@/components/cns/tap-test";
import { CoursesPanel } from "@/components/courses/courses-panel";
import { EntriesPanel } from "@/components/journal/entries-panel";
import { QuickSupplements } from "@/components/journal/quick-supplements";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("journal.metaTitle") };
}

export default async function JournalPage() {
  const { t } = await getI18n();
  const [presets, recent, bedtime, tests, entries] = await Promise.all([
    apiGet<Preset[]>("supplements/presets"),
    apiGet<SupplementLog[]>("supplements", { days: "1" }),
    apiGet<BedtimeReadout>("supplements/bedtime"),
    apiGet<CnsTest[]>("cns/tests", { limit: "30" }),
    apiGet<JournalEntry[]>("journal"),
  ]);
  return (
    <div className="space-y-12">
      <header>
        <h1 className="font-semibold">{t("journal.title")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("journal.intro")}</p>
      </header>
      <div className="grid gap-12 lg:grid-cols-2">
        <QuickSupplements presets={presets} initialRecent={recent} initialBedtime={bedtime} />
        <TapTest initial={tests} />
      </div>
      <CoursesPanel />
      <EntriesPanel initial={entries} />
    </div>
  );
}
