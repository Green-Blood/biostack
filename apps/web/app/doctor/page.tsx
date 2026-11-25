import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { Course, OrganIndex, OverviewMarker, Profile, RecordItem } from "@/lib/types";
import { VisitPack } from "@/components/doctor/visit-pack";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const { t } = await getI18n();
  return { title: t("doctor.metaTitle") };
}

export default async function DoctorSummaryPage() {
  const [profile, markers, courses, records, organIndex] = await Promise.all([
    apiGet<Profile>("profile").catch(() => null),
    apiGet<OverviewMarker[]>("biomarkers").catch(() => [] as OverviewMarker[]),
    apiGet<Course[]>("courses").catch(() => [] as Course[]),
    apiGet<RecordItem[]>("records").catch(() => [] as RecordItem[]),
    apiGet<OrganIndex>("organs").catch(() => ({ organs: [], unassigned: [] }) as OrganIndex),
  ]);
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

  return (
    <VisitPack
      profile={profile}
      markers={markers}
      courses={courses}
      records={records}
      organs={organIndex.organs}
      today={today}
    />
  );
}
