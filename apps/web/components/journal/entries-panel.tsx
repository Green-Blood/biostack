"use client";
import { useState } from "react";
import { useI18n } from "@/lib/i18n/client";
import type { JournalEntry } from "@/lib/types";
import { EntryForm } from "./entry-form";
import { EntryList } from "./entry-list";

const newestFirst = (a: JournalEntry, b: JournalEntry) => b.entry_date.localeCompare(a.entry_date) || b.id - a.id;

export function EntriesPanel({ initial }: { initial: JournalEntry[] }) {
  const [entries, setEntries] = useState(initial);
  const { t } = useI18n();
  return (
    <section aria-labelledby="journal-title" className="space-y-6">
      <h2 id="journal-title" className="font-semibold">{t("journal.entriesTitle")}</h2>
      <EntryForm onSaved={(entry) => setEntries((all) => [entry, ...all].sort(newestFirst))} />
      <EntryList entries={entries} onDeleted={(id) => setEntries((all) => all.filter((e) => e.id !== id))} />
    </section>
  );
}
