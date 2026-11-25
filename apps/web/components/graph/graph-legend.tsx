"use client";
import { useI18n } from "@/lib/i18n/client";
import { KINDS } from "./graph-node";

export function GraphLegend() {
  const { t } = useI18n();
  return (
    <section aria-label={t("graph.legend")} className="surface p-4 text-sm">
      <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {Object.entries(KINDS).map(([kind, { label, hint, Icon, shape }]) => (
          <li key={kind} className="flex items-center gap-3">
            <span className={`flex size-8 shrink-0 items-center justify-center bg-card ${shape}`}><Icon className="size-4" aria-hidden /></span>
            <span><span className="font-medium">{t(label)}</span> <span className="text-muted-foreground">{t(hint)}</span></span>
          </li>
        ))}
      </ul>
      <ul className="mt-4 grid gap-2 border-t pt-4 text-muted-foreground sm:grid-cols-2">
        <li>{t("graph.legendThick")}</li>
        <li>{t("graph.legendDashed")}</li>
        <li>{t("graph.legendColorBefore")} <span className="text-foreground">{t("graph.legendWorsens")}</span> {t("graph.legendColorMid")} <span className="text-foreground">{t("graph.legendImproves")}</span> {t("graph.legendColorAfter")}</li>
        <li>{t("graph.legendSelect")}</li>
        <li>{t("graph.legendDrag")}</li>
      </ul>
    </section>
  );
}
