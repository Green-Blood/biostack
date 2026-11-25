import { AskPanel } from "@/components/ask/ask-panel";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("ask.metaTitle") };
}

export default async function AskPage() {
  const { t } = await getI18n();
  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-semibold">{t("ask.title")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("ask.intro")}</p>
      </header>
      <AskPanel />
    </div>
  );
}
