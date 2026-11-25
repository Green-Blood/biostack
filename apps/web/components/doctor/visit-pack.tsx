"use client";
import Link from "next/link";
import { ArrowLeft, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n/client";
import type { Course, OrganSummary, OverviewMarker, Profile, RecordItem } from "@/lib/types";

type Props = {
  profile: Profile | null;
  markers: OverviewMarker[];
  courses: Course[];
  records: RecordItem[];
  organs: OrganSummary[];
  today: string;
};

function fmtRef(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return `${min} – ${max}`;
  if (max !== null) return `≤ ${max}`;
  if (min !== null) return `≥ ${min}`;
  return "—";
}

export function VisitPack({ profile, markers, courses, records, organs, today }: Props) {
  const { t, tp, formatDate, formatNumber } = useI18n();
  const outMarkers = markers.filter((m) => m.latest_value !== null && m.out_of_range_latest);
  const activeCourses = courses.filter((c) => c.status === "active" || c.status === "undated");
  const recentRecords = records.slice(0, 10);

  const sexLabel = profile?.sex === "male"
    ? t("doctor.sexMale")
    : profile?.sex === "female"
      ? t("doctor.sexFemale")
      : null;

  return (
    <div className="space-y-8 print:space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden /> {t("doctor.back")}
        </Link>
        <Button type="button" onClick={() => window.print()}>
          <Printer className="size-4" aria-hidden /> {t("doctor.print")}
        </Button>
      </div>

      <header className="space-y-2 border-b pb-5">
        <p className="eyebrow">{t("doctor.generatedOn", { date: formatDate(today) })}</p>
        <h1>{t("doctor.title")}</h1>
        <p className="max-w-prose text-sm text-muted-foreground">{t("doctor.subtitle")}</p>
        <div className="flex flex-wrap gap-2 pt-1 text-sm">
          {profile?.age_years != null && <Badge variant="secondary">{t("doctor.ageYears", { age: profile.age_years })}</Badge>}
          {sexLabel && <Badge variant="secondary">{sexLabel}</Badge>}
          {profile?.bmi && <Badge variant="secondary">{t("doctor.bmiLabel", { value: formatNumber(profile.bmi.value, { maximumFractionDigits: 1 }) })}</Badge>}
        </div>
      </header>

      <section aria-labelledby="doc-out-h" className="space-y-3 break-inside-avoid">
        <h2 id="doc-out-h" className="text-xl font-semibold">{t("doctor.outHeading")}</h2>
        {outMarkers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("doctor.outEmpty")}</p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40 text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">{t("doctor.colMarker")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("doctor.colValue")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("doctor.colRef")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("doctor.colDate")}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {outMarkers.map((m) => (
                  <tr key={m.marker_key}>
                    <td className="px-4 py-2.5 font-medium">{m.display_name}</td>
                    <td className="px-4 py-2.5 font-semibold text-outrange tnum">
                      {formatNumber(m.latest_value!, { maximumFractionDigits: 2 })} {m.unit}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground tnum">{fmtRef(m.ref_min, m.ref_max)}</td>
                    <td className="px-4 py-2.5 text-muted-foreground tnum">{m.latest_date ? formatDate(m.latest_date) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="doc-courses-h" className="space-y-3 break-inside-avoid">
        <h2 id="doc-courses-h" className="text-xl font-semibold">{t("doctor.coursesHeading")}</h2>
        {activeCourses.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("doctor.coursesEmpty")}</p>
        ) : (
          <ul className="surface divide-y overflow-hidden">
            {activeCourses.map((c) => (
              <li key={c.id} className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-sm">
                <div>
                  <span className="font-medium">{c.name}</span>
                  {c.dosage && <span className="ml-2 text-muted-foreground">{c.dosage}</span>}
                  {c.notes && <p className="mt-0.5 text-xs text-muted-foreground">{c.notes}</p>}
                </div>
                {c.start_date && <span className="text-xs text-muted-foreground tnum">{t("doctor.since", { date: formatDate(c.start_date) })}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="doc-records-h" className="space-y-3 break-inside-avoid">
        <h2 id="doc-records-h" className="text-xl font-semibold">{t("doctor.recordsHeading")}</h2>
        {recentRecords.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("doctor.recordsEmpty")}</p>
        ) : (
          <ul className="surface divide-y overflow-hidden">
            {recentRecords.map((r) => (
              <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <span className="font-medium">{r.title}</span>
                  {r.diagnoses && r.diagnoses.length > 0 && (
                    <span className="ml-2 text-xs text-muted-foreground">({r.diagnoses.join(", ")})</span>
                  )}
                </div>
                <span className="shrink-0 text-xs text-muted-foreground tnum">
                  {r.date ? formatDate(r.date) : t("common.noDate")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="doc-organs-h" className="space-y-3 break-inside-avoid">
        <h2 id="doc-organs-h" className="text-xl font-semibold">{t("doctor.organsHeading")}</h2>
        {organs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("doctor.organsEmpty")}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {organs.map((o) => (
              <li key={o.key} className="surface p-3.5 text-sm">
                <div className="font-medium">{o.name}</div>
                <div className="mt-1 text-xs text-muted-foreground tnum">
                  {tp("doctor.scansCount", o.scan_count)}
                  {o.latest_date ? ` · ${formatDate(o.latest_date)}` : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="border-t pt-4 text-xs text-muted-foreground">
        {t("doctor.disclaimer")}
      </footer>
    </div>
  );
}
