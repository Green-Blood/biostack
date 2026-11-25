"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bed, Clock, FileText, FlaskConical, ScanLine, Scissors, Stethoscope, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DemoBadge } from "@/components/demo-badge";
import { Input } from "@/components/ui/input";
import { AddVisitButton } from "@/components/records/add-visit-button";
import { spanLabel, isOngoing } from "@/components/records/meta";
import type { RecordItem } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";

const TYPES: Record<string, { label: Key; one: Key; dot: string; Icon: LucideIcon }> = {
  visit: { label: "timeline.typeVisits", one: "timeline.typeVisit", dot: "bg-chart-1", Icon: Stethoscope },
  hospital_stay: { label: "records.kindStays", one: "records.kindStay", dot: "bg-chart-2", Icon: Bed },
  lab: { label: "timeline.typeLab", one: "timeline.typeLabOne", dot: "bg-chart-5", Icon: FlaskConical },
  imaging: { label: "timeline.typeImaging", one: "timeline.typeImagingOne", dot: "bg-chart-4", Icon: ScanLine },
  procedure: { label: "timeline.typeProcedures", one: "timeline.typeProcedure", dot: "bg-chart-3", Icon: Scissors },
  other: { label: "timeline.typeOther", one: "timeline.typeOtherOne", dot: "bg-muted-foreground", Icon: FileText },
};

export function TimelineView({ records }: { records: RecordItem[] }) {
  const router = useRouter();
  const i18n = useI18n();
  const { t: tr, tp, formatDate, locale } = i18n;
  const monthLabel = (iso: string | null) => (iso ? formatDate(iso, { month: "long", year: "numeric" }) : tr("common.noDate"));
  const dayLabel = (iso: string | null) => (iso ? formatDate(iso, { day: "numeric", month: "short" }) : "—");
  const [type, setType] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const present = useMemo(() => Object.keys(TYPES).filter((t) => records.some((r) => r.record_type === t)), [records]);
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return records.filter(
      (r) => (!type || r.record_type === type) &&
        (!needle || `${r.title} ${r.details} ${r.doctors_note} ${r.clinic ?? ""} ${r.medications.join(" ")} ${(r.diagnoses ?? []).join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [records, type, q]);
  const years = useMemo(() => {
    const y = new Map<string, Map<string, RecordItem[]>>();
    for (const r of filtered) {
      const year = r.date ? r.date.slice(0, 4) : tr("common.noDate");
      const months = y.get(year) ?? new Map<string, RecordItem[]>();
      const month = monthLabel(r.date);
      months.set(month, [...(months.get(month) ?? []), r]);
      y.set(year, months);
    }
    return [...y.entries()].map(([year, months]) => ({ year, months: [...months.entries()] }));
  }, [filtered, locale]); // eslint-disable-line react-hooks/exhaustive-deps

  async function confirmDate(r: RecordItem) {
    if (!r.date) return;
    setBusy(r.id);
    setError(null);
    try {
      const res = await fetch("/api/review/date", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ record_id: r.id, confirmed_date: r.date }) });
      if (!res.ok) throw new Error(String(res.status));
      router.refresh();
    } catch {
      setError(tr("timeline.saveFailed"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("timeline.searchPlaceholder")} aria-label={tr("timeline.searchLabel")} className="max-w-xs bg-card" />
        <div role="group" aria-label={tr("timeline.filterLabel")} className="flex flex-wrap gap-1.5">
          <Button size="sm" className="rounded-full" variant={type === null ? "default" : "outline"} aria-pressed={type === null} onClick={() => setType(null)}>{tr("timeline.all", { n: records.length })}</Button>
          {present.map((t) => (
            <Button key={t} size="sm" className="rounded-full" variant={type === t ? "default" : "outline"} aria-pressed={type === t} onClick={() => setType(type === t ? null : t)}>
              <span className={`size-2 rounded-full ${type === t ? "bg-primary-foreground" : TYPES[t].dot}`} aria-hidden />
              {tr("timeline.typeCount", { label: tr(TYPES[t].label), n: records.filter((r) => r.record_type === t).length })}
            </Button>
          ))}
        </div>
      </div>

      {error && <p role="alert" className="rounded-2xl border border-outrange/50 bg-card p-3 text-sm">{error}</p>}
      {years.length === 0 && records.length === 0 && (
        <div className="empty-state space-y-4 p-8 text-center">
          <p className="mx-auto max-w-prose text-muted-foreground">{tr("records.timelineEmpty")}</p>
          <AddVisitButton label={tr("records.addVisit")} />
        </div>
      )}
      {years.length === 0 && records.length > 0 && <p className="empty-state p-8 text-center text-muted-foreground">{tr("timeline.empty")}</p>}

      {years.map(({ year, months }) => (
        <section key={year} aria-label={year}>
          <h2 className="tnum sticky top-0 z-10 -mx-1 border-b bg-background/90 px-1 py-2 text-2xl backdrop-blur">{year}</h2>
          {months.map(([month, items]) => (
          <div key={month} className="mt-4">
          <h3 className="eyebrow mb-3 first-letter:uppercase">{month}</h3>
          <ol className="relative ml-2 border-l pl-6">
            {items.map((r) => {
              const ty = TYPES[r.record_type] ?? TYPES.other;
              const range = r.end_date || isOngoing(r) ? spanLabel(r, i18n, true) : null;
              const dx = r.diagnoses ?? [];
              return (
                <li key={r.id} id={`record-${r.id}`} className="relative scroll-mt-16 pb-6 last:pb-2">
                  <span className={`absolute -left-[31px] top-2 size-2.5 rounded-full ring-4 ring-background ${ty.dot}`} aria-hidden />
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="tnum w-16 text-sm text-muted-foreground">{dayLabel(r.date)}</span>
                    <Link href={`/records/${r.id}`} className="min-w-0 break-words rounded-md text-left text-base font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">{r.title}</Link>
                    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground"><ty.Icon className="size-3.5" aria-hidden />{r.clinic ? tr("timeline.atClinic", { type: tr(ty.one), clinic: r.clinic }) : tr(ty.one)}</span>
                  </div>
                  <div className="ml-[4.75rem] mt-1.5 flex flex-wrap items-center gap-1.5">
                    {isOngoing(r) && <Badge variant="default" className="gap-1"><Clock aria-hidden />{tr("records.statusOngoing")}</Badge>}
                    {range && <span className="tnum text-sm text-muted-foreground">{range}</span>}
                    {dx.slice(0, 3).map((d) => <Badge key={d} variant="outline" className="max-w-[12rem] truncate">{d}</Badge>)}
                    {dx.length > 3 && <Badge variant="secondary">+{dx.length - 3}</Badge>}
                    {r.is_demo && <DemoBadge />}
                    {r.has_labs && <Badge variant={r.out_of_range_count ? "destructive" : "secondary"}>{r.out_of_range_count ? tr("timeline.outOfRange", { n: r.out_of_range_count }) : tr("timeline.labsInRange")}</Badge>}
                    {r.attachment_count > 0 && <Badge variant="secondary">{tp("timeline.files", r.attachment_count)}</Badge>}
                    {(r.organs ?? []).map((o) => (
                      <Link key={o.key} href={`/organs/${o.key}`} className="rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
                        <Badge variant="secondary" className="hover:bg-accent"><ScanLine aria-hidden />{o.name}</Badge>
                      </Link>
                    ))}
                    {r.medications.map((m) => <Badge key={m} variant="outline">{m}</Badge>)}
                    {r.date_suspect && (
                      <>
                        <Badge variant="outline" className="border-warn/60 text-warn">{tr("common.dateUnverified")}</Badge>
                        {r.date && <Button size="xs" variant="ghost" disabled={busy === r.id} onClick={() => confirmDate(r)}>{tr("timeline.confirmDate")}</Button>}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          </div>
          ))}
        </section>
      ))}
    </div>
  );
}
