import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { GraphData } from "@/lib/types";
import { GraphView } from "@/components/graph/graph-view";

export default async function GraphPage() {
  const { t } = await getI18n();
  const graph = await apiGet<GraphData>("analytics/graph").catch(() => null);
  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-semibold">{t("graph.title")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">
          {t("graph.intro")}
        </p>
      </header>
      <GraphView initial={graph} />
    </div>
  );
}
