import Link from "next/link";
import { ArrowRight, FileText, Paperclip } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { Course, Freshness, OverviewMarker, Profile, RecordItem } from "@/lib/types";
import { ProfileOverviewCard } from "@/components/profile/overview-card";
import { RetestBlock } from "@/components/dashboard/retest-block";
import { Badge } from "@/components/ui/badge";
import { AttentionBlock } from "@/components/dashboard/attention-block";
import { SectionHeader } from "@/components/dashboard/section-header";
import { SystemsGrid } from "@/components/dashboard/systems-grid";
import { HospitalCard } from "@/components/dashboard/hospital-card";
import { AddVisitButton } from "@/components/records/add-visit-button";
import { AiHealthCard } from "@/components/dashboard/ai-health-card";
import { BodyMapCard } from "@/components/dashboard/body-map-card";
import { TodayPanel } from "@/components/dashboard/today-panel";
import { SignalsStrip } from "@/components/dashboard/signals-strip";
import { OnboardingCard } from "@/components/dashboard/onboarding-card";
import { getI18n } from "@/lib/i18n/server";

export default async function Overview() {
  const { t, tp, formatDate, formatNumber } = await getI18n();
  const fmt = (iso: string | null) => (iso ? formatDate(iso, { day: "numeric", month: "short" }) : t("common.noDate"));
  // Freshness and courses are additive: if the API cannot answer, fall back to the /biomarkers ages and hide the block.
  const [markers, records, freshness, courses, profile] = await Promise.all([
    apiGet<OverviewMarker[]>("biomarkers"), apiGet<RecordItem[]>("records"),
    apiGet<Freshness>("freshness").catch(() => null), apiGet<Course[]>("courses").catch(() => [] as Course[]),
    apiGet<Profile>("profile").catch(() => null),
  ]);
  const numeric = markers.filter((m) => m.latest_value !== null);

  // Everything below is computed from stored results; nothing is estimated.
  // Each marker is judged by its OWN latest result: an old low vitamin D still counts when TSH alone was measured yesterday.
  const outLatest = numeric.filter((m) => m.out_of_range_latest);
  const stale = freshness
    ? freshness.items.filter((i) => i.status !== "fresh")
    : numeric.filter((m) => m.retest_days != null && m.age_days != null && m.age_days > m.retest_days);
  const parts = [
    outLatest.length > 0 ? tp("overview.statusOut", outLatest.length) : null,
    stale.length > 0 ? tp("overview.statusStale", stale.length) : null,
  ].filter((p): p is string => p !== null);
  const statusText = numeric.length === 0 ? t("overview.statusNoData") : parts.length > 0 ? parts.join(t("overview.statusJoin")) : t("overview.statusAllGood");
  const tone = numeric.length === 0 ? "bg-muted-foreground" : outLatest.length > 0 ? "bg-outrange" : stale.length > 0 ? "bg-warn" : "bg-ok";

  const moved = numeric
    .filter((m) => m.spark.length >= 2 && m.spark.at(-2) !== 0)
    .map((m) => ({ m, pct: ((m.spark.at(-1)! - m.spark.at(-2)!) / Math.abs(m.spark.at(-2)!)) * 100 }))
    .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct))
    .slice(0, 5);
  const now = new Date();
  const localDay = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const today = formatDate(freshness?.today ?? localDay, { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-10">
      <header className="space-y-3">
        <p className="eyebrow first-letter:uppercase">{today}</p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1>{t("overview.title")}</h1>
          <AddVisitButton label={t("records.addVisit")} variant="outline" />
        </div>
        <p role="status" className="surface flex items-start gap-3 px-4 py-3 text-base">
          <span className={`mt-2 size-2.5 shrink-0 rounded-full ${tone}`} aria-hidden />
          <span>
            <span className="font-medium">{statusText}</span>
            {numeric.length > 0 && numeric.length < 5 && <span className="mt-0.5 block text-sm text-muted-foreground">{t("overview.statusFewData")}</span>}
            <span className="mt-0.5 block text-sm text-muted-foreground tnum">
              {tp("overview.recordsCount", records.length)} · {tp("overview.markersNumeric", numeric.length)}
            </span>
          </span>
        </p>
      </header>

      {records.length === 0 && numeric.length === 0 && <OnboardingCard profile={profile} />}

      {numeric.length > 0 && <AiHealthCard />}

      <BodyMapCard markers={markers} records={records} profile={profile} />


      <HospitalCard records={records} />

      <ProfileOverviewCard profile={profile} />

      <SignalsStrip />

      {numeric.length > 0 && <AttentionBlock markers={outLatest} />}

      {freshness && <RetestBlock items={freshness.items} courses={courses} />}

      <SystemsGrid markers={markers} />

      <TodayPanel />

      <div className="grid gap-10 lg:grid-cols-2">
        <section aria-labelledby="recent-h" className="min-w-0">
          <SectionHeader id="recent-h" title={t("overview.latestRecords")} />
          {records.length === 0 ? (
            <div className="empty-state space-y-3 p-6 text-muted-foreground"><p>{t("overview.noRecords")}</p><AddVisitButton label={t("records.addVisit")} /></div>
          ) : (
            <ul className="surface divide-y overflow-hidden">
              {records.slice(0, 6).map((r) => (
                <li key={r.id} className="flex items-center gap-3 px-4 py-3">
                  <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="tnum w-14 shrink-0 text-sm text-muted-foreground">{fmt(r.date)}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">{r.title}</span>
                  {r.attachment_count > 0 && (
                    <Badge variant="secondary" className="shrink-0 gap-1" title={tp("overview.recordFiles", r.attachment_count)}>
                      <Paperclip className="size-3" aria-hidden />{r.attachment_count}
                    </Badge>
                  )}
                  {r.date_suspect && <Badge variant="outline" className="shrink-0 border-warn/60 text-warn">{t("common.dateUnverified")}</Badge>}
                </li>
              ))}
            </ul>
          )}
          <Link href="/timeline" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">{t("overview.openTimeline")}<ArrowRight className="size-3.5" aria-hidden /></Link>
        </section>

        <section aria-labelledby="moved-h" className="min-w-0">
          <SectionHeader id="moved-h" title={t("overview.movedHeading")} />
          {moved.length === 0 ? (
            <p className="empty-state p-6 text-muted-foreground">{t("overview.movedEmpty")}</p>
          ) : (
            <ul className="surface divide-y overflow-hidden">
              {moved.map(({ m, pct }) => (
                <li key={m.marker_key}>
                  <Link href={`/biomarkers/${encodeURIComponent(m.marker_key)}`} className="flex items-baseline gap-3 px-4 py-3 transition-colors hover:bg-accent/50">
                    <span className="font-medium">{m.display_name}</span>
                    <span className="tnum ml-auto">{pct > 0 ? "+" : "−"}{formatNumber(Math.abs(pct), { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link href="/biomarkers" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">{t("overview.openBiomarkers")}<ArrowRight className="size-3.5" aria-hidden /></Link>
        </section>
      </div>
    </div>
  );
}
