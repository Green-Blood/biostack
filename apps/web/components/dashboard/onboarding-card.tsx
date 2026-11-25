import Link from "next/link";
import { CheckCircle2, FilePlus, Settings, UserRound } from "lucide-react";
import type { Profile } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";

export async function OnboardingCard({ profile }: { profile: Profile | null }) {
  const { t } = await getI18n();
  const profileReady = Boolean(profile?.sex && profile?.birth_date);

  return (
    <section aria-labelledby="onboard-h" className="surface space-y-5 p-6">
      <div className="space-y-1">
        <h2 id="onboard-h">{t("overview.onboardTitle")}</h2>
        <p className="max-w-prose text-sm text-muted-foreground">{t("overview.onboardSub")}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="flex flex-col justify-between gap-4 rounded-2xl border bg-background/60 p-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 font-medium">
              {profileReady ? <CheckCircle2 className="size-4 text-ok" aria-hidden /> : <UserRound className="size-4 text-primary" aria-hidden />}
              <span>{t("overview.onboardStep1Title")}</span>
            </div>
            <p className="text-sm text-muted-foreground">
              {profileReady ? t("overview.onboardStep1Done") : t("overview.onboardStep1Desc")}
            </p>
          </div>
          <Link href="/profile" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            {t("overview.onboardStep1Action")} →
          </Link>
        </div>

        <div className="flex flex-col justify-between gap-4 rounded-2xl border bg-background/60 p-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 font-medium">
              <FilePlus className="size-4 text-primary" aria-hidden />
              <span>{t("overview.onboardStep2Title")}</span>
            </div>
            <p className="text-sm text-muted-foreground">{t("overview.onboardStep2Desc")}</p>
          </div>
          <div className="flex flex-wrap gap-3 text-sm font-medium">
            <Link href="/labs/new" className="text-primary underline-offset-4 hover:underline">{t("overview.onboardStep2Action")} →</Link>
            <Link href="/records/new" className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">{t("overview.onboardStep2Visit")}</Link>
          </div>
        </div>

        <div className="flex flex-col justify-between gap-4 rounded-2xl border bg-background/60 p-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 font-medium">
              <Settings className="size-4 text-primary" aria-hidden />
              <span>{t("overview.onboardStep3Title")}</span>
            </div>
            <p className="text-sm text-muted-foreground">{t("overview.onboardStep3Desc")}</p>
          </div>
          <Link href="/settings" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            {t("overview.onboardStep3Action")} →
          </Link>
        </div>
      </div>

      <div className="space-y-1 border-t pt-3 text-xs text-muted-foreground">
        <p>{t("overview.onboardDemoHint")}</p>
        <p>{t("overview.onboardDisclaimer")}</p>
      </div>
    </section>
  );
}
