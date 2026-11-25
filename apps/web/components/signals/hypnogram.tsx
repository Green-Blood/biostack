"use client";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChartWidth } from "@/components/charts/use-chart-width";
import { useI18n } from "@/lib/i18n/client";
import { getJson } from "@/lib/request";
import type { SleepDetail, SleepNight } from "@/lib/types";
import { duration } from "./format";
import { clockIso, hypnogram, isStaged, STAGE, STAGES } from "./sleep-model";

const ROW = 34;
const BAR = 18;
const ROWS = [...STAGES].sort((a, b) => a.level - b.level); // awake, REM, light, deep (top to bottom)

function NightChart({ detail }: { detail: SleepDetail }) {
  const i18n = useI18n();
  const { t, formatDate, formatTime } = i18n;
  const [ref, width] = useChartWidth();
  const compact = width < 520;
  const left = compact ? 92 : 112, right = width - 12, top = 8, bottom = top + ROW * ROWS.length;
  const g = hypnogram(detail.stages, detail.session.start_local, detail.session.end_local);
  const x = (m: number) => left + (m / g.span) * (right - left);
  const pxPerHour = ((right - left) / g.span) * 60;
  const every = pxPerHour >= 44 ? 1 : pxPerHour >= 22 ? 2 : 3;
  const rowY = (level: number) => top + ROW * level + ROW / 2;
  const list = STAGES.map((s) => t("signals.stageTime", { name: t(s.label), time: duration(i18n, detail.session[s.key]).long })).join(", ");
  const label = t("signals.hypLabel", { date: formatDate(detail.session.wake_date, { day: "numeric", month: "long", year: "numeric" }), list });
  return (
    <div ref={ref} className="w-full max-w-full overflow-hidden">
      <svg width={width} height={bottom + 26} role="img" aria-label={label} className="block font-sans">
        <g aria-hidden>
          {ROWS.map((s) => (
            <g key={s.key}>
              <line x1={left} x2={right} y1={rowY(s.level)} y2={rowY(s.level)} className="stroke-border" strokeOpacity={0.5} strokeDasharray="2 4" />
              <circle cx={10} cy={rowY(s.level)} r={4} style={{ fill: s.color }} />
              <text x={20} y={rowY(s.level) + 4} className="fill-muted-foreground text-[11px]">{t(s.label)}</text>
            </g>
          ))}
          {g.hours.filter((h) => h.clock % (every * 60) === 0).map((h) => (
            <g key={h.x}>
              <line x1={x(h.x)} x2={x(h.x)} y1={top} y2={bottom + 4} className="stroke-border" strokeOpacity={0.5} />
              <text x={x(h.x)} y={bottom + 18} textAnchor="middle" className="fill-muted-foreground text-[11px] tnum">{formatTime(clockIso(h.clock))}</text>
            </g>
          ))}
          {g.links.map((l) => (
            <line key={`l${l.x}`} x1={x(l.x)} x2={x(l.x)} y1={rowY(Math.min(l.from, l.to))} y2={rowY(Math.max(l.from, l.to))} className="stroke-muted-foreground" strokeOpacity={0.45} strokeWidth={1} />
          ))}
          {g.segments.map((s) => (
            <rect key={`${s.stage}${s.x0}`} x={x(s.x0)} y={rowY(STAGE[s.stage].level) - BAR / 2} width={Math.max(1, x(s.x1) - x(s.x0))} height={BAR} rx={Math.min(4, (x(s.x1) - x(s.x0)) / 2)} style={{ fill: STAGE[s.stage].color, stroke: "color-mix(in oklab, var(--foreground) 35%, transparent)" }} strokeWidth={0.75} />
          ))}
        </g>
      </svg>
    </div>
  );
}

type Props = { nights: SleepNight[]; selectedId: number | null; initial: SleepDetail | null; onSelect: (id: number) => void };

/** The selected night (the latest by default) as a hypnogram, fetched on demand and kept for the visit. */
export function Hypnogram({ nights, selectedId, initial, onSelect }: Props) {
  const i18n = useI18n();
  const { t, formatDate, formatTime } = i18n;
  const [cache, setCache] = useState<Record<number, SleepDetail>>(() => (initial ? { [initial.session.session_id]: initial } : {}));
  const [failed, setFailed] = useState<{ id: number; message: string } | null>(null);
  const idx = nights.findIndex((n) => n.session_id === selectedId);
  const night = idx >= 0 ? nights[idx] : null;
  const detail = selectedId !== null ? cache[selectedId] : undefined;

  useEffect(() => {
    if (selectedId === null || cache[selectedId]) return;
    let live = true;
    getJson<SleepDetail>(`signals/sleep/${selectedId}`)
      .then((d) => { if (live) setCache((c) => ({ ...c, [selectedId]: d })); })
      .catch((e: Error) => { if (live) setFailed({ id: selectedId, message: e.message }); });
    return () => { live = false; };
  }, [selectedId, cache]);

  if (!night) return null;
  const earlier = nights[idx + 1], later = nights[idx - 1];
  const total = duration(i18n, night.duration_min);
  return (
    <section id="night-detail" aria-labelledby="night-h" className="scroll-mt-6 space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="space-y-1">
          <h2 id="night-h" className="text-2xl font-semibold">{t("signals.hypTitle")}</h2>
          <p className="text-sm text-muted-foreground tnum" aria-live="polite">
            {t("signals.wokeUp", { date: formatDate(night.wake_date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) })}
            {" · "}{t("signals.inBed", { start: formatTime(night.start_local), end: formatTime(night.end_local) })}
            {" · "}<span aria-label={`${t("signals.asleepLabel")}: ${total.long}`}>{t("signals.asleepLabel")} {total.short} {t("signals.hoursUnit")}</span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={!earlier} onClick={() => earlier && onSelect(earlier.session_id)}><ChevronLeft aria-hidden />{t("signals.hypPrev")}</Button>
          <Button variant="outline" size="sm" disabled={!later} onClick={() => later && onSelect(later.session_id)}>{t("signals.hypNext")}<ChevronRight aria-hidden /></Button>
        </div>
      </div>
      <div className="surface min-w-0 space-y-3 p-4">
        {detail ? (
          detail.stages.length ? <NightChart detail={detail} /> : <p className="text-sm text-muted-foreground">{t("signals.stagesNone")}</p>
        ) : failed?.id === selectedId ? (
          <p role="alert" className="text-sm text-muted-foreground">{failed.message}</p>
        ) : (
          <p className="h-40 text-sm text-muted-foreground" aria-busy>{t("signals.hypLoading")}</p>
        )}
        {isStaged(night) && <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          {STAGES.map((s) => (
            <li key={s.key} className="min-w-0 space-y-0.5">
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><span className="size-2.5 shrink-0 rounded-full" style={{ background: s.color }} />{t(s.label)}</span>
              <span className="block text-sm font-medium tnum">{duration(i18n, night[s.key]).short}</span>
            </li>
          ))}
        </ul>}
        <p className="text-xs text-muted-foreground">
          {night.parts > 1 && `${t("signals.hypParts", { n: night.parts })} `}{t("signals.hypNote")}
        </p>
      </div>
    </section>
  );
}
