import { notFound } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { OrganDetail, Profile } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { DoctorView, type Patient } from "@/components/organs/doctor-view";

async function load<T>(path: string): Promise<T | null> {
  try { return await apiGet<T>(path); } catch { return null; }
}

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }) {
  const { t } = await getI18n();
  const organ = await load<OrganDetail>(`organs/${encodeURIComponent(decodeURIComponent((await params).key))}`);
  return { title: organ ? `${organ.name} · ${t("organs.doctorTitle")}` : t("organs.pageTitle") };
}

/** The organ's history for an appointment: a clean, light, printable sheet. Only age and sex come from the profile. */
export default async function DoctorPage({ params }: { params: Promise<{ key: string }> }) {
  const key = decodeURIComponent((await params).key);
  const [organ, profile] = await Promise.all([load<OrganDetail>(`organs/${encodeURIComponent(key)}`), load<Profile>("profile")]);
  if (!organ) notFound();
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  // Nothing else from the profile reaches the client: no birth date, height, weight or BMI.
  const patient: Patient = { age: profile?.birth_date ? profile.age_years : null, sex: profile?.sex ?? null };
  return <DoctorView organ={organ} patient={patient} today={today} />;
}
