import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { BmiHistory, BodyMeasurement, BodySnapshot, Measurement, Profile } from "@/lib/types";
import { ProfileView } from "@/components/profile/profile-view";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("profile.metaTitle") };
}

export default async function ProfilePage() {
  // Each part fails on its own: the page shows what it has and says plainly what it could not load.
  const [profile, weights, waists, history, body, measurements] = await Promise.all([
    apiGet<Profile>("profile").catch(() => null),
    apiGet<Measurement[]>("profile/measurements", { kind: "weight" }).catch(() => [] as Measurement[]),
    apiGet<Measurement[]>("profile/measurements", { kind: "waist" }).catch(() => [] as Measurement[]),
    apiGet<BmiHistory>("profile/bmi-history").catch(() => null),
    apiGet<BodySnapshot>("profile/body").catch(() => null),
    apiGet<BodyMeasurement[]>("profile/measurements").catch(() => null),
  ]);
  return <ProfileView initial={{ profile, weights, waists, history, body, measurements }} />;
}
