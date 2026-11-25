import Link from "next/link";
import { notFound } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { Context, MarkerHistory, MarkerHistoryExtras, MarkerSummary } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { HistoryView } from "@/components/biomarkers/history-view";

export default async function MarkerPage({ params }: { params: Promise<{ key: string }> }) {
  const { t } = await getI18n();
  const { key } = await params;
  const marker = decodeURIComponent(key);
  let history: MarkerHistory & MarkerHistoryExtras;
  try { history = await apiGet<MarkerHistory & MarkerHistoryExtras>(`biomarkers/${encodeURIComponent(marker)}/history`); } catch { notFound(); }
  const dates = history.points.map((p) => p.date).sort();
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const [context, all] = await Promise.all([
    apiGet<Context>("context", { from: dates[0], to: dates.length && dates.at(-1)! > today ? dates.at(-1) : today }),
    apiGet<MarkerSummary[]>("biomarkers"),
  ]);
  return (
    <div className="space-y-6">
      <header>
        <Link href="/biomarkers" className="text-sm text-muted-foreground underline-offset-4 hover:underline">{t("biomarkers.title")}</Link>
        <h1 className="mt-1 text-4xl font-semibold">{history.display_name}</h1>
      </header>
      <HistoryView h={history} context={context} today={today} others={all.filter((m) => m.count > 0).map((m) => ({ marker_key: m.marker_key, display_name: m.display_name }))} />
    </div>
  );
}
