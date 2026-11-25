import { apiGet } from "@/lib/api";
import type { SignalsOverview as Overview } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { SignalsOverview } from "@/components/signals/overview";
import { SignalsHeader } from "@/components/signals/signals-nav";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("signals.pageTitle") };
}

export default async function SignalsPage() {
  const { t } = await getI18n();
  const data = await apiGet<Overview>("signals/overview");
  return (
    <div className="space-y-6">
      <SignalsHeader current="overview" title={t("signals.title")} intro={t("signals.intro")} />
      <SignalsOverview data={data} />
    </div>
  );
}
