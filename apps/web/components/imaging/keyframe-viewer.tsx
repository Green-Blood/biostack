"use client";
import { useState } from "react";
import Image from "next/image";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ImagingStudy } from "@/lib/types";
import { useI18n } from "@/lib/i18n/client";

const frameUrl = (studyId: number, index: number) => `/api/imaging/${studyId}/frames/${index}`;

/** Large keyframe on a dark stage with a thumbnail strip; arrow keys, Home and End move between frames. */
export function KeyframeViewer({ study }: { study: ImagingStudy }) {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  const last = study.frame_count - 1;
  const go = (next: number) => setIndex(Math.min(Math.max(next, 0), last));
  const label = `${study.study_type}${study.body_part ? `, ${study.body_part}` : ""}`;

  function onKeyDown(e: React.KeyboardEvent) {
    const target: Record<string, number> = { ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1, ArrowDown: index + 1, Home: 0, End: last };
    if (!(e.key in target)) return;
    e.preventDefault();
    go(target[e.key]);
  }

  if (study.frame_count === 0) return <p className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">{t("imaging.noKeyframes")}</p>;

  return (
    <section aria-label={t("imaging.keyframesLabel")} className="space-y-3">
      <div
        tabIndex={0} onKeyDown={onKeyDown} aria-label={t("imaging.keyframeAria", { i: index + 1, total: study.frame_count })}
        className="relative flex min-h-64 items-center justify-center overflow-hidden rounded-2xl bg-black outline-none focus-visible:ring-3 focus-visible:ring-ring/60"
      >
        <Image key={index} unoptimized src={frameUrl(study.id, index)} width={1024} height={1024} priority
          alt={t("imaging.keyframeAlt", { label, i: index + 1, total: study.frame_count })} className="h-auto max-h-[70vh] w-auto max-w-full object-contain" />
        <span className="tnum absolute bottom-3 left-3 rounded bg-black/60 px-2 py-1 text-xs text-white" aria-hidden>{index + 1} / {study.frame_count}</span>
        <Button type="button" variant="secondary" size="icon" className="absolute top-1/2 left-2 -translate-y-1/2 opacity-90" onClick={() => go(index - 1)} disabled={index === 0} aria-label={t("imaging.previousKeyframe")}><ChevronLeft aria-hidden /></Button>
        <Button type="button" variant="secondary" size="icon" className="absolute top-1/2 right-2 -translate-y-1/2 opacity-90" onClick={() => go(index + 1)} disabled={index === last} aria-label={t("imaging.nextKeyframe")}><ChevronRight aria-hidden /></Button>
      </div>
      <ul aria-label={t("imaging.thumbnails")} className="flex gap-2 overflow-x-auto pb-1">
        {Array.from({ length: study.frame_count }, (_, i) => (
          <li key={i} className="shrink-0">
            <button type="button" onClick={() => setIndex(i)} aria-label={t("imaging.showKeyframe", { i: i + 1 })} aria-current={i === index ? "true" : undefined}
              className={`block overflow-hidden rounded-xl bg-black outline-none focus-visible:ring-3 focus-visible:ring-ring/60 ${i === index ? "ring-2 ring-[var(--data)]" : "opacity-70 hover:opacity-100"}`}>
              <Image unoptimized src={frameUrl(study.id, i)} width={96} height={96} alt="" className="size-20 object-cover" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
