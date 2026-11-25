import { apiGet } from "@/lib/api";
import type { Context, SignalSeriesMap } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { HeartView } from "@/components/signals/heart-view";
import { firstDate, HEART_KEYS } from "@/components/signals/metric-model";
import { SignalsHeader } from "@/components/signals/signals-nav";
import { StaleNote } from "@/components/signals/stale-note";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("heart.pageTitle") };
}

/** Every day is loaded once (a few years of daily values is a small list); the period selector only changes the view. */
const ALL_FROM = "2000-01-01";

export default async function HeartPage() {
  const { t } = await getI18n();
  // No `to`: the API ends at its own today (configured zone) and says which day that is.
  const data = await apiGet<SignalSeriesMap>("signals/series", { keys: HEART_KEYS.join(","), from: ALL_FROM });
  const today = data.today;
  const first = firstDate(Object.values(data.series));
  const context = first ? await apiGet<Context>("context", { from: first, to: today }).catch(() => null) : null;
  return (
    <div className="space-y-6">
      <SignalsHeader current="heart" title={t("heart.title")} intro={t("heart.intro")} />
      <StaleNote freshness={data} />
      <HeartView data={data} context={context} />
    </div>
  );
}
