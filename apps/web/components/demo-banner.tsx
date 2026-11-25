import { apiGet } from "@/lib/api";
import type { DemoStatus } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";

export async function DemoBanner() {
  const status = await apiGet<DemoStatus>("meta/demo").catch(() => null);
  if (!status?.demo) return null;
  const { t } = await getI18n();
  return (
    <div role="status" className="border-b border-data/40 bg-accent px-4 py-2 text-center text-sm">
      <span className="font-medium">{t("common.demoBannerTitle")}</span> {t("common.demoBannerBody")}
    </div>
  );
}
