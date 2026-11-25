import { apiGet } from "@/lib/api";
import type { Briefing, Risk } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { BriefingCard } from "./briefing-card";
import { Recommendations } from "./recommendations";
import { RiskMeter } from "./risk-meter";

/** Risk and briefing for the top of the overview. A failure here must never hide the rest of the page. */
export async function TodayPanel() {
  const { t, locale } = await getI18n();
  const [risk, briefing] = await Promise.all([
    apiGet<Risk>("analytics/risk").catch(() => null),
    apiGet<Briefing>("analytics/briefing").catch(() => null),
  ]);
  if (!risk && !briefing) {
    return <p role="status" className="empty-state p-4 text-muted-foreground">{t("overview.todayLoadFailed")}</p>;
  }
  return (
    <div className="space-y-6">
      {risk?.alert && <Recommendations items={risk.recommendations} />}
      <div className="grid items-start gap-6 lg:grid-cols-2">
        {risk && <RiskMeter risk={risk} />}
        {briefing && <BriefingCard key={locale} initial={briefing} />}
      </div>
    </div>
  );
}
