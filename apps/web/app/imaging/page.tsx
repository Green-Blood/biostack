import { apiGet } from "@/lib/api";
import type { ImagingStudy } from "@/lib/types";
import { ImagingView } from "@/components/imaging/imaging-view";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("imaging.pageTitle") };
}

export default async function ImagingPage() {
  const { t } = await getI18n();
  const studies = await apiGet<ImagingStudy[]>("imaging");
  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-semibold">{t("imaging.heading")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("imaging.intro")}</p>
      </header>
      <ImagingView initial={studies} />
    </div>
  );
}
