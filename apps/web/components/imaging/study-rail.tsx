import type { ImagingStudy } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";

type Props = { studies: ImagingStudy[]; selectedId: number | null; onSelect: (id: number) => void };

/** Dated rail like the timeline: newest first, grouped by year. */
export function StudyRail({ studies, selectedId, onSelect }: Props) {
  const { t, tp, formatDate } = useI18n();
  const years = [...new Set(studies.map((s) => s.study_date.slice(0, 4)))];
  return (
    <nav aria-label={t("imaging.studiesLabel")} className="max-h-72 space-y-4 overflow-y-auto lg:max-h-none">
      {years.map((year) => (
        <section key={year} aria-label={year}>
          <h2 className="py-1 text-xl">{year}</h2>
          <ol className="relative ml-2 border-l pl-5">
            {studies.filter((s) => s.study_date.startsWith(year)).map((s) => {
              const active = s.id === selectedId;
              return (
                <li key={s.id} className="relative pb-3 last:pb-1">
                  <span className={`absolute -left-[26px] top-3 size-2.5 rounded-full ring-4 ring-background ${active ? "bg-[var(--data)]" : "bg-muted-foreground/60"}`} aria-hidden />
                  <button type="button" onClick={() => onSelect(s.id)} aria-current={active ? "true" : undefined}
                    className={`block w-full rounded-xl px-3 py-2 text-left outline-none transition-colors hover:bg-accent/60 focus-visible:ring-3 focus-visible:ring-ring/50 ${active ? "bg-accent" : ""}`}>
                    <span className="tnum block text-sm text-muted-foreground">{formatDate(s.study_date)}</span>
                    <span className="block font-medium">{s.study_type}{s.body_part ? `, ${s.body_part}` : ""}</span>
                    <span className="tnum block text-sm text-muted-foreground">{tp("imaging.keyframes", s.frame_count)}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </nav>
  );
}
