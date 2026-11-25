"use client";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { sendJson } from "@/lib/request";
import type { BodyKind, BodyMeasurement } from "@/lib/types";
import { cn } from "cn";
import { KINDS, metaOf } from "./body-kinds";

const LIMIT = 10;

export function MeasurementsList({ rows, onChanged }: { rows: BodyMeasurement[]; onChanged: () => void }) {
  const { t, formatDate, formatNumber, unit } = useI18n();
  const [confirm, setConfirm] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [filter, setFilter] = useState<BodyKind | null>(null);
  const present = KINDS.filter((k) => rows.some((r) => r.kind === k.kind));
  const active = filter && present.some((k) => k.kind === filter) ? filter : null;
  const sorted = rows.filter((r) => !active || r.kind === active).sort((a, b) => b.date.localeCompare(a.date) || a.kind.localeCompare(b.kind));
  const shown = all ? sorted : sorted.slice(0, LIMIT);

  async function remove(id: number) {
    setBusy(true); setError(null);
    try { await sendJson(`profile/measurements/${id}`, "DELETE"); setConfirm(null); onChanged(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  if (!rows.length) return <p className="empty-state p-5 text-muted-foreground">{t("profile.measurementsEmpty")}</p>;
  return (
    <div className="space-y-3">
      {present.length > 1 && (
        <div role="group" aria-label={t("profile.filterLabel")} className="flex flex-wrap gap-2">
          {[{ kind: null, label: t("profile.filterAll") }, ...present.map((k) => ({ kind: k.kind as BodyKind | null, label: t(k.label) }))].map((c) => (
            <button key={c.kind ?? "all"} type="button" aria-pressed={active === c.kind} onClick={() => { setFilter(c.kind); setConfirm(null); setAll(false); }}
              className={cn("h-8 rounded-full border px-3.5 text-sm outline-none transition-[background-color,transform] duration-200 focus-visible:ring-3 focus-visible:ring-ring/50 active:scale-[0.97] motion-reduce:transition-none",
                active === c.kind ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>{c.label}</button>
          ))}
        </div>
      )}
      {!sorted.length && <p className="empty-state p-5 text-muted-foreground">{t("profile.filterEmpty")}</p>}
      <ul className="surface divide-y overflow-hidden empty:hidden">
        {shown.map((m) => {
          const meta = metaOf(m.kind);
          const kind = t(meta.label);
          const value = `${formatNumber(m.value, { maximumFractionDigits: meta.digits })} ${unit(meta.unit)}`;
          const date = formatDate(m.date);
          return (
            <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 text-sm">
              <span className="w-28 shrink-0 text-muted-foreground tnum">{date}</span>
              <span className="min-w-0 flex-1"><span className="text-muted-foreground">{kind}</span> <span className="font-medium tnum">{value}</span></span>
              {confirm === m.id ? (
                <span className="flex flex-wrap items-center gap-2" role="group" aria-label={t("profile.confirmDelete")}>
                  <span>{t("profile.confirmDelete")}</span>
                  <Button type="button" size="sm" variant="destructive" disabled={busy} onClick={() => remove(m.id)} autoFocus>{busy ? t("profile.deleting") : t("profile.confirmYes")}</Button>
                  <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => setConfirm(null)}>{t("profile.confirmNo")}</Button>
                </span>
              ) : (
                <Button type="button" size="icon-sm" variant="ghost" onClick={() => { setError(null); setConfirm(m.id); }} aria-label={t("profile.deleteEntry", { kind, value, date })}><Trash2 aria-hidden /></Button>
              )}
            </li>
          );
        })}
      </ul>
      {sorted.length > LIMIT && <Button type="button" variant="outline" size="sm" onClick={() => setAll((v) => !v)}>{all ? t("profile.showLess") : t("profile.showAll", { n: sorted.length })}</Button>}
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
    </div>
  );
}
