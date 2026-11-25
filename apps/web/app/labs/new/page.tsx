import { apiGet } from "@/lib/api";
import type { MarkerSummary, RecordOut } from "@/lib/types";
import { Inbox } from "@/components/labs/inbox";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("labs.pageTitle") };
}

export default async function NewLabsPage() {
  const { t, locale } = await getI18n();
  const [catalog, stored, records] = await Promise.all([
    apiGet<string[]>("labs/marker-names"), apiGet<MarkerSummary[]>("biomarkers"), apiGet<RecordOut[]>("records"),
  ]);
  const names = [...new Set([...catalog, ...stored.map((m) => m.display_name)])].sort((a, b) => a.localeCompare(b, locale));
  const recent = records.slice(0, 200).map((r) => ({ id: r.id, title: r.title, date: r.date }));
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-4xl font-semibold">{t("labs.heading")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("labs.intro")}</p>
      </header>
      <Inbox markerNames={names} records={recent} />
    </div>
  );
}
