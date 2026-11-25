import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { EnvironmentReading, Preset, UserSettings } from "@/lib/types";
import { AiSetting } from "@/components/settings/ai-setting";
import { DataExport } from "@/components/settings/data-export";
import { EnvironmentCard } from "@/components/settings/environment-card";
import { PresetsEditor } from "@/components/settings/presets-editor";
import { ProfileForm } from "@/components/settings/profile-form";
import { AppleHealthCard } from "@/components/settings/apple-health-card";
import { SamsungImportCard } from "@/components/signals/import-card";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("settings.metaTitle") };
}

export default async function SettingsPage() {
  const { t } = await getI18n();
  const [profile, presets, readings] = await Promise.all([
    apiGet<UserSettings>("settings"),
    apiGet<Preset[]>("supplements/presets"),
    apiGet<EnvironmentReading[]>("environment", { limit: "1" }),
  ]);
  const sections = [
    { id: "profile", title: t("settings.profileTitle"), body: <ProfileForm initial={profile} /> },
    { id: "presets", title: t("settings.presetsTitle"), body: <PresetsEditor initial={presets} /> },
    { id: "environment", title: t("settings.environmentTitle"), body: <EnvironmentCard initial={readings[0] ?? null} /> },
    { id: "samsung", title: t("signals.importTitle"), body: <SamsungImportCard /> },
    { id: "apple", title: t("settings.appleTitle"), body: <AppleHealthCard /> },
    { id: "ai", title: t("settings.aiTitle"), body: <AiSetting aiBriefing={profile.ai_briefing} /> },
    { id: "export", title: t("settings.exportTitle"), body: <DataExport /> },
  ];
  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-semibold">{t("settings.title")}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{t("settings.intro")}</p>
      </header>
      {sections.map((s) => (
        <section key={s.id} id={s.id} aria-labelledby={`${s.id}-title`} className="space-y-4 border-t pt-6">
          <h2 id={`${s.id}-title`} className="text-2xl font-semibold">{s.title}</h2>
          {s.body}
        </section>
      ))}
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-6 text-sm text-muted-foreground">
        <span>{t("settings.communityNote")}</span>
        <a href="https://github.com/Green-Blood/biostack/issues/new?template=feature_request.md" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-foreground">
          {t("settings.suggestFeature")}
        </a>
        <a href="https://strangen.gumroad.com/l/biostack-coffee" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-foreground">
          {t("settings.buyCoffee")}
        </a>
      </footer>
    </div>
  );
}
