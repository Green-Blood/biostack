import { notFound } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { RecordDetail } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { RecordView } from "@/components/records/record-view";

export default async function RecordPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ focus?: string | string[] }> }) {
  const { id } = await params;
  const { focus } = await searchParams;
  const { t } = await getI18n();
  if (!/^\d+$/.test(id)) notFound();
  let record: RecordDetail | null = null;
  try { record = await apiGet<RecordDetail>(`records/${id}`); } catch { /* shown below */ }
  if (!record) {
    return (
      <div className="mx-auto max-w-3xl space-y-3">
        <h1 className="font-semibold">{t("records.loadFailedTitle")}</h1>
        <p role="alert" className="surface p-4">{t("records.loadFailed")}</p>
      </div>
    );
  }
  return <RecordView key={record.id} initial={record} focusNote={focus === "note"} />;
}
