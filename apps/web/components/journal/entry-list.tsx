"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { sendJson } from "@/lib/request";
import type { JournalCategory, JournalEntry } from "@/lib/types";
import { CATEGORIES } from "./entry-form";

type Props = { entries: JournalEntry[]; onDeleted: (id: number) => void };

export function EntryList({ entries, onDeleted }: Props) {
  const { t, formatDate } = useI18n();
  const [filter, setFilter] = useState<JournalCategory | "all">("all");
  const [confirming, setConfirming] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const shown = filter === "all" ? entries : entries.filter((e) => e.category === filter);
  const labelOf = (c: JournalCategory) => { const found = CATEGORIES.find((x) => x.value === c); return found ? t(found.label) : c; };

  async function remove(id: number) {
    setError(null);
    try { await sendJson(`journal/${id}`, "DELETE"); onDeleted(id); } catch (e) { setError((e as Error).message); }
    setConfirming(null);
  }

  return (
    <div className="space-y-4">
      <div role="group" aria-label={t("journal.filterLabel")} className="flex flex-wrap gap-2">
        {[{ value: "all" as const, label: "journal.filterAll" as Key }, ...CATEGORIES].map((c) => (
          <Button key={c.value} size="sm" variant={filter === c.value ? "secondary" : "outline"} aria-pressed={filter === c.value} onClick={() => setFilter(c.value)}>{t(c.label)}</Button>
        ))}
      </div>
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
      {shown.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">{entries.length === 0 ? t("journal.emptyAll") : t("journal.emptyFilter")}</p>
      ) : (
        <ul className="divide-y">
          {shown.map((e) => (
            <li key={e.id} className="flex items-start justify-between gap-4 py-3">
              <div className="min-w-0 space-y-0.5">
                <p className="tnum text-sm text-muted-foreground">{formatDate(e.entry_date)} · {labelOf(e.category)}</p>
                <p className="font-medium">{e.title}</p>
                {(e.severity_1_10 !== null || e.body_location) && (
                  <p className="text-sm text-muted-foreground">
                    {e.severity_1_10 !== null && <span className="tnum">{t("journal.severityShort", { value: e.severity_1_10 })}</span>}
                    {e.severity_1_10 !== null && e.body_location && " · "}{e.body_location}
                  </p>
                )}
                {e.description && <p className="whitespace-pre-line text-sm">{e.description}</p>}
              </div>
              {confirming === e.id
                ? <Button size="sm" variant="destructive" className="h-auto min-h-7 shrink-0 whitespace-normal py-1" onClick={() => remove(e.id)} onBlur={() => setConfirming(null)} autoFocus>{t("journal.confirmDelete")}</Button>
                : <Button size="sm" variant="ghost" onClick={() => setConfirming(e.id)} aria-label={t("journal.deleteAria", { title: e.title })}>{t("journal.delete")}</Button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
