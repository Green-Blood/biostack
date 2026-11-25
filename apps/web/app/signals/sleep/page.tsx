import { apiGet } from "@/lib/api";
import type { Context, SleepDetail, SleepList } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { SleepView } from "@/components/signals/sleep-view";
import { SignalsHeader } from "@/components/signals/signals-nav";
import { StaleNote } from "@/components/signals/stale-note";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("signals.sleepPageTitle") };
}

/** Every night is loaded once (a few years of nights is a small list); the period selector only changes the view. */
const ALL_FROM = "2000-01-01";

export default async function SleepPage() {
  const { t } = await getI18n();
  const data = await apiGet<SleepList>("signals/sleep", { from: ALL_FROM });
  const today = data.today; // the API's today, in the configured zone (not this server's clock)
  const newest = data.nights[0];
  const oldest = data.nights.at(-1);
  const [context, detail] = newest
    ? await Promise.all([
        apiGet<Context>("context", { from: oldest!.wake_date, to: today }),
        apiGet<SleepDetail>(`signals/sleep/${newest.session_id}`).catch(() => null),
      ])
    : [null, null];
  return (
    <div className="space-y-6">
      <SignalsHeader current="sleep" title={t("signals.sleepTitle")} intro={t("signals.sleepIntro")} />
      <StaleNote freshness={data} />
      <SleepView data={data} context={context} initialDetail={detail} today={today} />
    </div>
  );
}
