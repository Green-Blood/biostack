import { apiGet } from "@/lib/api";
import type { Context, SignalSeriesMap, WorkoutList } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { ActivityView } from "@/components/signals/activity-view";
import { ACTIVITY_KEYS, firstDate } from "@/components/signals/metric-model";
import { SignalsHeader } from "@/components/signals/signals-nav";
import { StaleNote } from "@/components/signals/stale-note";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("activity.pageTitle") };
}

/** All days and workouts are loaded once; the period selector and the type filter only change the view. */
const ALL_FROM = "2000-01-01";

export default async function ActivityPage() {
  const { t } = await getI18n();
  // No `to`: the API ends at its own today (configured zone) and says which day that is.
  const [data, workouts] = await Promise.all([
    apiGet<SignalSeriesMap>("signals/series", { keys: ACTIVITY_KEYS.join(","), from: ALL_FROM }),
    apiGet<WorkoutList>("signals/workouts", { from: ALL_FROM }),
  ]);
  const today = data.today;
  const first = [firstDate(Object.values(data.series)), workouts.items.at(-1)?.local_date ?? null].filter((d): d is string => !!d).sort()[0];
  const context = first ? await apiGet<Context>("context", { from: first, to: today }).catch(() => null) : null;
  return (
    <div className="space-y-6">
      <SignalsHeader current="activity" title={t("activity.title")} intro={t("activity.intro")} />
      <StaleNote freshness={data} />
      <ActivityView data={data} workouts={workouts} context={context} />
    </div>
  );
}
