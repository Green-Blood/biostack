import Link from "next/link";
import { ArrowRight, UserRound } from "lucide-react";
import { getI18n } from "@/lib/i18n/server";
import type { Profile } from "@/lib/types";
import { CATEGORY_KEY } from "./category";

/** Overview teaser: a one-line invitation until birth date and sex are set, then a compact summary. */
export async function ProfileOverviewCard({ profile }: { profile: Profile | null }) {
  const { t, tp, formatDate, formatNumber } = await getI18n();
  if (!profile) return null;
  const complete = profile.birth_date !== null && profile.sex !== null;
  if (!complete) {
    return (
      <Link href="/profile" className="surface surface-interactive flex items-center gap-3 px-4 py-3 text-sm motion-reduce:transition-none">
        <UserRound className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1">{t("profile.ovInvite")}</span>
        <ArrowRight className="size-4 shrink-0" aria-hidden />
      </Link>
    );
  }
  const bmi = profile.bmi;
  return (
    <Link href="/profile" aria-label={t("profile.ovOpen")} className="surface surface-interactive flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 motion-reduce:transition-none">
      <span className="eyebrow inline-flex items-center gap-1.5"><UserRound className="size-3.5" aria-hidden />{t("profile.ovTitle")}</span>
      {profile.age_years != null && <span className="text-sm tnum">{tp("profile.age", profile.age_years)}</span>}
      {bmi && <span className="text-sm tnum">{t("profile.ovBmi")} <span className="font-semibold">{formatNumber(bmi.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span> · {t(CATEGORY_KEY[bmi.category])}</span>}
      {profile.latest_weight && <span className="text-sm text-muted-foreground tnum">{t("profile.ovWeightOn", { date: formatDate(profile.latest_weight.date) })}</span>}
      <ArrowRight className="ml-auto size-4 shrink-0" aria-hidden />
    </Link>
  );
}
