import { apiGet } from "@/lib/api";
import type { RecordItem } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { NewRecord } from "@/components/records/new-record";

export default async function NewRecordPage() {
  const { t } = await getI18n();
  // The clinic suggestions are a convenience: the form works without them.
  const records = await apiGet<RecordItem[]>("records").catch(() => [] as RecordItem[]);
  const clinics = [...new Set(records.map((r) => r.clinic?.trim()).filter((c): c is string => !!c))].sort((a, b) => a.localeCompare(b));
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="font-semibold">{t("records.newTitle")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("records.newIntro")}</p>
      </header>
      <NewRecord clinics={clinics} />
    </div>
  );
}
