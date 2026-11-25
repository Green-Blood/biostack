"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FileText, Printer } from "lucide-react";
import { cn } from "cn";
import { DEFAULT_PERIOD, periodDomain } from "@/components/charts/period";
import { dayMs } from "@/components/charts/time-scale";
import { useI18n } from "@/lib/i18n/client";
import type { OrganDetail, ProfileSex, ScanColumn, Treatment } from "@/lib/types";
import { fileUrl, Verbatim } from "./conclusions";
import { ScanCell, usePrevText } from "./scan-cell";
import { ParamLabel } from "./scan-table";
import { SeriesCharts } from "./series-charts";
import { buildContext, rowGroups, shownUnit, type Param } from "./table-model";

/** The only profile facts this view may show; both are optional. */
export type Patient = { age: number | null; sex: ProfileSex | null };

/** Scan columns per printed table: with the repeated first column this fits an A4 portrait page. */
const PRINT_COLUMNS = 4;
const FIRST_COL = "sticky left-0 z-10 w-40 min-w-40 max-w-40 bg-card shadow-[1px_0_0_var(--border)] sm:w-52 sm:min-w-52 sm:max-w-52 print:static print:shadow-none";
const isThumb = (mime: string) => mime === "image/jpeg" || mime === "image/png";

function chunks<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** Parameters × scans, every value printed (no hover), every scan shown; a parameter's rows never split across pages. */
function StaticTable({ params, scans, prevText }: { params: Param[]; scans: ScanColumn[]; prevText: Map<string, string | null> }) {
  const { t, formatDate } = useI18n();
  const groups = useMemo(() => rowGroups(params), [params]);
  return (
    <table className="w-max border-separate border-spacing-0 text-sm">
      <thead>
        <tr>
          <th scope="col" className={cn(FIRST_COL, "z-20 border-b px-3 py-2 text-left align-bottom font-medium text-muted-foreground")}>{t("organs.colParam")}</th>
          {scans.map((s) => (
            <th key={s.record_id} scope="col" className="border-b px-3 py-2 text-right align-bottom font-semibold whitespace-nowrap tnum">
              {s.date ? formatDate(s.date) : t("organs.noDate")}
              {s.date_suspect && <span className="ml-0.5 text-warn" title={t("organs.dateUnconfirmed")}>?</span>}
            </th>
          ))}
        </tr>
      </thead>
      {groups.map((g) => (
        <tbody key={g.param_key} className="break-inside-avoid">
          {g.rows.map((p, k) => {
            const last = k === g.rows.length - 1;
            return (
              <tr key={p.series_key} className="break-inside-avoid">
                <th scope="row" className={cn(FIRST_COL, "px-3 py-2 text-left align-top font-normal", last && "border-b")}><ParamLabel p={p} first={k === 0} /></th>
                {scans.map((s) => (
                  <ScanCell key={s.record_id} staticMode v={s.values[p.series_key]} prevText={prevText.get(`${s.record_id}|${p.series_key}`) ?? null} className={last ? "border-b" : ""} />
                ))}
              </tr>
            );
          })}
        </tbody>
      ))}
    </table>
  );
}

function CourseDates({ tr }: { tr: Treatment }) {
  const { t, formatDate } = useI18n();
  return <>{tr.end ? t("organs.doctorCourseDates", { start: formatDate(tr.start), end: formatDate(tr.end) }) : t("organs.doctorCourseOngoing", { start: formatDate(tr.start) })}</>;
}

/** The numbers recorded for one scan, marked like the table when not verified yet. */
function ScanNumbers({ scan, params }: { scan: ScanColumn; params: Param[] }) {
  const { t, formatNumber, unit } = useI18n();
  const rows = params.filter((p) => scan.values[p.series_key]);
  if (!rows.length) return null;
  return (
    <div>
      <div className="eyebrow mb-1">{t("organs.doctorNumbers")}</div>
      <ul className="flex flex-wrap gap-x-6 gap-y-1">
        {rows.map((p) => {
          const v = scan.values[p.series_key];
          const name = p.side ? t("organs.seriesSide", { name: p.name, side: t(p.side === "left" ? "organs.sideLeft" : "organs.sideRight") }) : p.name;
          const u = v.value !== null ? unit(shownUnit(v.unit)) : "";
          return (
            <li key={p.series_key} className={v.verified ? "" : "italic"}>
              {name}: <span className="font-semibold tnum">{v.value !== null ? formatNumber(v.value, { maximumFractionDigits: 2 }) : v.value_text}</span>
              {u && <span className="text-muted-foreground"> {u}</span>}
              {!v.verified && <span className="ml-1 font-semibold not-italic text-muted-foreground" title={t("organs.legendUnverified")}>?</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ConclusionCard({ scan, params, aliases }: { scan: ScanColumn; params: Param[]; aliases: string[] }) {
  const { t, formatDate } = useI18n();
  const details = scan.details?.trim() ?? "", note = scan.doctors_note?.trim() ?? "", body = scan.body_markdown?.trim() ?? "";
  const thumbs = scan.attachments.filter((f) => isThumb(f.mime_type)), files = scan.attachments.filter((f) => !isThumb(f.mime_type));
  return (
    <li className="doctor-avoid space-y-3 border-t pt-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="font-sans text-xl font-semibold tnum">{scan.date ? formatDate(scan.date) : t("organs.noDate")}</h3>
        {scan.date_suspect && <span className="rounded-full border border-warn/60 px-2 py-0.5 text-xs text-warn">{t("organs.dateUnconfirmed")}</span>}
        <span className="min-w-0 break-words text-muted-foreground">{scan.title}</span>
      </div>
      {details || note || body ? (
        <>
          {details && <Verbatim text={details} aliases={aliases} className="text-[17px]" />}
          {note && (
            <div>
              <div className="eyebrow mb-1">{t("organs.doctorsNote")}</div>
              <Verbatim text={note} aliases={aliases} className="text-[17px]" />
            </div>
          )}
          {body && <Verbatim text={body} aliases={aliases} className="text-[17px]" />}
        </>
      ) : <p className="text-muted-foreground">{t("organs.noConclusion")}</p>}
      <ScanNumbers scan={scan} params={params} />
      {scan.attachments.length > 0 && (
        <div>
          <div className="eyebrow mb-1.5">{t("organs.doctorFiles")}</div>
          {thumbs.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-4">
              {thumbs.map((f) => (
                <a key={f.id} href={fileUrl(f.id)} target="_blank" rel="noreferrer" className="block max-w-40 text-sm text-primary underline-offset-4 hover:underline">
                  {/* eslint-disable-next-line @next/next/no-img-element -- served by our own API; it must also load for printing */}
                  <img src={fileUrl(f.id)} alt={f.filename} className="block max-h-40 max-w-40 rounded-lg border object-contain" />
                  <span className="mt-1 block break-all">{f.filename}</span>
                </a>
              ))}
            </div>
          )}
          {files.length > 0 && (
            <ul className="space-y-1">
              {files.map((f) => (
                <li key={f.id}>
                  <a href={fileUrl(f.id)} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-2 break-all text-primary underline underline-offset-4">
                    <FileText aria-hidden className="size-4 shrink-0" />{f.filename}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

/** "Show to doctor": a full-screen, always-light sheet over the app that prints cleanly. Nothing here is saved. */
export function DoctorView({ organ, patient, today }: { organ: OrganDetail; patient: Patient; today: string }) {
  const { t, tp, formatDate } = useI18n();
  const todayMs = dayMs(today);
  const [hidden, setHidden] = useState<Set<number>>(() => new Set());
  const shown = useMemo(() => organ.treatments.filter((_, i) => !hidden.has(i)), [organ.treatments, hidden]);
  const context = useMemo(() => buildContext({ ...organ, treatments: shown }, false), [organ, shown]);
  const domain = useMemo(() => periodDomain(DEFAULT_PERIOD, organ.series.flatMap((s) => s.points.map((p) => dayMs(p.date))), todayMs), [organ.series, todayMs]);
  const prevText = usePrevText(organ.scans);
  const toggle = (i: number) => setHidden((prev) => { const next = new Set(prev); if (next.has(i)) next.delete(i); else next.add(i); return next; });

  const first = organ.scans.find((s) => s.date)?.date;
  const facts = [
    t("organs.doctorToday", { date: formatDate(today) }),
    patient.age !== null && t("organs.doctorAge", { n: patient.age }),
    patient.sex && t("organs.doctorSex", { sex: t(patient.sex === "female" ? "profile.sexFemale" : "profile.sexMale") }),
    organ.scans.length > 0 && tp("organs.scans", organ.scans.length),
  ].filter(Boolean);
  const hasNumbers = organ.params.length > 0;
  const anySuspect = organ.scans.some((s) => s.date_suspect);

  return (
    <div data-theme="clinic" className="doctor-view fixed inset-0 z-50 overflow-y-auto bg-background text-foreground">
      <div className="doctor-no-print sticky top-0 z-30 border-b bg-background">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-2.5">
          <Link href={`/organs/${encodeURIComponent(organ.key)}`} className="inline-flex h-11 items-center gap-2 rounded-xl border px-4 font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
            <ArrowLeft aria-hidden className="size-5" />{t("organs.doctorBack")}
          </Link>
          <button type="button" onClick={() => window.print()} className="inline-flex h-11 items-center gap-2 rounded-xl bg-primary px-4 font-medium text-primary-foreground outline-none hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
            <Printer aria-hidden className="size-5" />{t("organs.doctorPrint")}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-4xl space-y-12 px-4 pt-8 pb-16">
        <header className="space-y-2 border-b pb-6">
          <p className="eyebrow">{t("organs.doctorTitle")}</p>
          <h1 className="break-words text-4xl font-semibold">{organ.name}</h1>
          {first && <p className="text-xl tnum">{t("organs.doctorPeriod", { from: formatDate(first), to: formatDate(today) })}</p>}
          <p className="text-muted-foreground tnum">{facts.join(" · ")}</p>
        </header>

        {organ.scans.length === 0 && <p className="text-muted-foreground">{t("organs.emptyScans")}</p>}
        {organ.scans.length > 0 && !hasNumbers && <p className="text-muted-foreground">{t("organs.doctorNoNumbers")}</p>}

        {organ.series.length > 0 && (
          <section aria-labelledby="d-charts" className="space-y-4">
            <h2 id="d-charts" className="text-3xl">{t("organs.chartsTitle")}</h2>
            <SeriesCharts organ={organ} context={context} domain={domain} todayMs={todayMs} staticMode />
          </section>
        )}

        {hasNumbers && (
          <section aria-labelledby="d-table" className="min-w-0 space-y-3">
            <h2 id="d-table" className="text-3xl">{t("organs.tableTitle")}</h2>
            <p className="text-muted-foreground">{t("organs.doctorTableHint")}</p>
            {/* On screen: one table that scrolls inside its own box. In print: blocks of a few scans, the first column repeated. */}
            <div className="surface relative max-w-full overflow-x-auto overscroll-x-contain print:hidden" role="region" tabIndex={0} aria-label={t("organs.tableTitle")}>
              <StaticTable params={organ.params} scans={organ.scans} prevText={prevText} />
            </div>
            <div className="hidden space-y-4 print:block">
              {chunks(organ.scans, PRINT_COLUMNS).map((part) => (
                <div key={part[0].record_id} className="doctor-table-part relative">
                  <StaticTable params={organ.params} scans={part} prevText={prevText} />
                </div>
              ))}
            </div>
            <p className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
              <span><span className="rounded bg-chart-4/15 px-1">{t("organs.legendChange")}</span></span>
              <span className="italic">{t("organs.legendUnverified")}</span>
              {anySuspect && <span><span className="text-warn">?</span> {t("organs.dateUnconfirmed")}</span>}
            </p>
            <p className="max-w-prose text-sm text-muted-foreground">{t("organs.measurementsVary")}</p>
          </section>
        )}

        {organ.scans.length > 0 && (
          <section aria-labelledby="d-treatments" className="space-y-3">
            <h2 id="d-treatments" className="text-3xl">{t("organs.doctorTreatmentsTitle")}</h2>
            {organ.treatments.length === 0 ? <p className="text-muted-foreground">{t("organs.doctorTreatmentsEmpty")}</p> : (
              <>
                <p className="doctor-no-print text-sm text-muted-foreground">{t("organs.doctorTreatmentsHint")}</p>
                <ul aria-label={t("organs.doctorTreatmentsLabel")} className="space-y-2">
                  {organ.treatments.map((tr, i) => hidden.has(i) ? null : (
                    <li key={i} className="doctor-avoid">
                      <label className="flex cursor-pointer items-start gap-3">
                        <input type="checkbox" checked onChange={() => toggle(i)} className="doctor-no-print mt-1 size-5 shrink-0 accent-primary" />
                        <span className="min-w-0">
                          <span className="font-semibold">{tr.name}</span>{tr.dosage && <span>, {tr.dosage}</span>}
                          {tr.related && <span className="ml-2 inline-block rounded-full border px-2 text-sm text-muted-foreground">{t("organs.doctorRelated")}</span>}
                          <span className="block text-muted-foreground tnum"><CourseDates tr={tr} /></span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
                {hidden.size > 0 && (
                  <div className="doctor-no-print flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <span>{t("organs.doctorLeftOut")}</span>
                    {organ.treatments.map((tr, i) => hidden.has(i) && (
                      <button key={i} type="button" onClick={() => toggle(i)} className="rounded-full border px-3 py-1 text-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
                        {t("organs.doctorPutBack", { name: tr.name })}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        )}

        {organ.scans.length > 0 && (
          <section aria-labelledby="d-visits" className="space-y-3">
            <h2 id="d-visits" className="text-3xl">{t("organs.doctorVisitsTitle")}</h2>
            {organ.visits.length === 0 ? <p className="text-muted-foreground">{t("organs.doctorVisitsEmpty")}</p> : (
              <ul className="space-y-1.5">
                {organ.visits.map((v) => (
                  <li key={v.id} className="doctor-avoid flex flex-wrap gap-x-4">
                    <span className="w-44 shrink-0 font-medium tnum">{formatDate(v.date)}</span>
                    <span className="min-w-0 break-words">{v.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {organ.scans.length > 0 && (
          <section aria-labelledby="d-conclusions" className="space-y-3">
            <h2 id="d-conclusions" className="text-3xl">{t("organs.doctorConclusionsTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("organs.doctorConclusionsHint")}</p>
            <ul className="space-y-6">
              {organ.scans.map((s) => <ConclusionCard key={s.record_id} scan={s} params={organ.params} aliases={organ.aliases} />)}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
