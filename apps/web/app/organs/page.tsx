import { apiGet } from "@/lib/api";
import type { OrganIndex } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { OrgansIndex } from "@/components/organs/organs-index";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("organs.pageTitle") };
}

export default async function OrgansPage() {
  const { t } = await getI18n();
  const data = await apiGet<OrganIndex>("organs");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-4xl font-semibold">{t("organs.title")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("organs.intro")}</p>
      </header>
      <OrgansIndex data={data} />
    </div>
  );
}
