"use client";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { Effect, GraphEdge } from "@/lib/types";

export const EFFECT_COLOR: Record<Effect, string> = { worsens: "var(--outrange)", improves: "var(--data)", unclear: "var(--muted-foreground)" };
const EFFECT_VARIANT: Record<Effect, "destructive" | "secondary" | "outline"> = { worsens: "destructive", improves: "secondary", unclear: "outline" };

const BADGE: Record<Effect, Key> = { worsens: "graph.badgeWorsens", improves: "graph.badgeImproves", unclear: "graph.badgeUnclear" };

type Props = { edges: GraphEdge[]; focusedLabel: string | null };

/** What each link says in words, and how much data stands behind it. */
export function EdgeDetails({ edges, focusedLabel }: Props) {
  const { t, formatNumber } = useI18n();
  const formatChance = (p: number) => (p < 0.001 ? t("graph.chanceLow") : t("graph.chance", { p: formatNumber(p, { minimumFractionDigits: 3, maximumFractionDigits: 3 }) }));
  return (
    <section aria-labelledby="edges-h" className="surface p-5">
      <h2 id="edges-h">{focusedLabel ? t("graph.detailsTitleFocused", { label: focusedLabel }) : t("graph.detailsTitle")}</h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        {t("graph.detailsHelp")}
      </p>
      <ul className="mt-3 divide-y">
        {edges.map((e) => (
          <li key={e.id} className="space-y-1 py-3">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-medium">
              <span>{e.phrase}</span>
              <Badge variant={EFFECT_VARIANT[e.effect]}>{t(BADGE[e.effect])}</Badge>
            </p>
            <p className="tnum text-sm text-muted-foreground">
              {t("graph.seenOn", { days: e.n_days, chance: formatChance(e.p_value), strength: formatNumber(e.strength, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) })}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
