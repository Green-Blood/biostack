"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorLine, SectionCard, Chip } from "@/components/records/kit";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { OrganCatalogEntry, ScanExtractReport, ScanExtractResult, ScanTags } from "@/lib/types";
import { ScanActions } from "./scan-actions";
import { OrganRows } from "./scan-organ-rows";
import { buildPut, changed, draftFromRows, filledCells, mergeServer, tagKeys, type Draft } from "./scan-model";

type Busy = "" | "rule" | "ai" | "save";

/** Organ tags and the measurement editor for an imaging record. Edits stay in this component until "Save and verify". */
export function ScanPanel({ recordId }: { recordId: number }) {
  const { t, tp, formatNumber } = useI18n();
  const fmt = useCallback((n: number) => formatNumber(n, { maximumFractionDigits: 4, useGrouping: false }), [formatNumber]);
  const [catalog, setCatalog] = useState<OrganCatalogEntry[] | null>(null);
  const [organs, setOrgans] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft>({});
  const [bad, setBad] = useState<Set<string>>(new Set());
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<Busy>("");
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null); // organ whose numbers would be dropped, awaiting a yes

  const load = useCallback((tags: ScanTags) => { setOrgans(tagKeys(tags)); setDraft(draftFromRows(tags.measurements, fmt)); setDirty(false); }, [fmt]);
  useEffect(() => {
    let live = true;
    Promise.all([getJson<OrganCatalogEntry[]>("organs/catalog"), getJson<ScanTags>(`scans/${recordId}`)])
      .then(([c, tags]) => { if (live) { setCatalog(c); load(tags); } })
      .catch((e: Error) => { if (live) setError(e.message || t("organs.scanLoadFailed")); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordId]);

  const byKey = useMemo(() => new Map((catalog ?? []).map((o) => [o.key, o])), [catalog]);

  function edit(key: string, text: string) {
    setDraft((d) => ({ ...d, [key]: { text, origin: d[key]?.origin ?? "manual", verified: false, edited: true, stored: d[key]?.stored ?? null } }));
    setBad((b) => { if (!b.has(key)) return b; const n = new Set(b); n.delete(key); return n; });
    setDirty(true); setSaved(false);
  }
  const flip = (key: string) => { setOrgans((o) => (o.includes(key) ? o.filter((k) => k !== key) : [...o, key])); setDirty(true); setSaved(false); };
  /** Removing an organ that holds values drops them on Save, so it asks first; an empty organ goes at once. */
  const toggle = (key: string) => {
    if (organs.includes(key) && filledCells(key, draft) > 0) { setRemoving(key); return; }
    if (removing === key) setRemoving(null);
    flip(key);
  };
  const confirmRemove = () => { if (removing) flip(removing); setRemoving(null); };

  const summary = (r: ScanExtractReport, ai: boolean) => !changed(r) && r.skipped_verified === 0 && ai ? t("organs.scanAiNothing")
    : t(ai ? "organs.scanAiDone" : "organs.scanExtractDone", { added: r.added, kept: r.skipped_verified }) + (r.updated ? ` ${t("organs.scanExtractUpdated", { updated: r.updated })}` : "");

  async function read(ai: boolean) {
    setBusy(ai ? "ai" : "rule"); setError(null); setSaved(false);
    try {
      const res = await sendJson<ScanExtractResult>(`scans/${recordId}/extract${ai ? "?ai=1" : ""}`, "POST");
      const lines = [!changed(res.report) && res.report.skipped_verified === 0 ? t("organs.scanExtractNothing") : summary(res.report, false)];
      if (res.ai_report) lines.push(summary(res.ai_report, true));
      const server = draftFromRows(res.measurements, fmt);
      const kept = Object.values(draft).some((c) => c.edited);
      setDraft(mergeServer(draft, server));
      setOrgans((o) => [...new Set([...o, ...tagKeys(res)])]);
      if (kept) lines.push(t("organs.scanExtractKeptEdits"));
      setNotes(lines);
    } catch (e) {
      setError((e as Error).message);
      // A failed AI read can follow a rule read the server already saved: take those rows in (local edits stay
      // exactly as they were), or the next Save would send the old draft and delete them.
      try {
        const tags = await getJson<ScanTags>(`scans/${recordId}`);
        setDraft((d) => mergeServer(d, draftFromRows(tags.measurements, fmt)));
        setOrgans((o) => [...new Set([...o, ...tagKeys(tags)])]);
      } catch { /* the error above already tells the owner something went wrong */ }
    } finally { setBusy(""); }
  }

  async function save() {
    const built = buildPut(organs, catalog ?? [], draft);
    if ("bad" in built) { setBad(new Set(built.bad)); setError(t("organs.scanBadNumber")); return; }
    setBusy("save"); setError(null); setBad(new Set()); setNotes([]);
    try { load(await sendJson<ScanTags>(`scans/${recordId}`, "PUT", built.body)); setSaved(true); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  return (
    <SectionCard id="organs" title={t("organs.scanTitle")} count={organs.length}>
      <p className="text-sm text-muted-foreground">{t("organs.scanHint")}</p>
      {catalog && (
        <div role="group" aria-label={t("organs.scanAddOrgan")} className="flex flex-wrap gap-2">
          {catalog.map((o) => <Chip key={o.key} on={organs.includes(o.key)} disabled={busy !== ""} onClick={() => toggle(o.key)}>{o.name}</Chip>)}
        </div>
      )}
      {removing && (
        <div role="alertdialog" aria-labelledby="scan-remove-ask" className="space-y-3 rounded-2xl border bg-card/60 p-3">
          <p id="scan-remove-ask" className="text-sm">{tp("organs.scanRemoveAsk", filledCells(removing, draft), { name: byKey.get(removing)?.name ?? removing })}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="lg" variant="destructive" onClick={confirmRemove}>{t("organs.scanRemoveYes")}</Button>
            <Button type="button" size="lg" variant="outline" onClick={() => setRemoving(null)}>{t("organs.scanRemoveCancel")}</Button>
          </div>
        </div>
      )}
      {catalog && organs.length === 0 && <p className="empty-state p-4 text-sm text-muted-foreground">{t("organs.scanNoOrgans")}</p>}
      <div className="space-y-3">
        {organs.map((k) => byKey.get(k)).filter((o): o is OrganCatalogEntry => !!o).map((o) => (
          <OrganRows key={o.key} organ={o} draft={draft} bad={bad} onChange={edit} onRemove={() => toggle(o.key)} disabled={busy !== ""} />
        ))}
      </div>
      <ErrorLine message={error} />
      {catalog && <ScanActions busy={busy} onRule={() => read(false)} onAi={() => read(true)} onSave={save} />}
      <div aria-live="polite" className="space-y-1 text-sm">
        {dirty && <p className="text-muted-foreground">{t("organs.scanDirty")}</p>}
        {notes.map((n) => <p key={n}>{n}</p>)}
        {saved && <p role="status">{t("organs.scanSaved")}</p>}
      </div>
      {saved && organs.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {organs.map((k) => (
            <li key={k}><Link href={`/organs/${encodeURIComponent(k)}`} className="inline-flex min-h-11 items-center rounded-full border bg-card px-4 text-sm font-medium hover:bg-muted">{t("organs.scanSeeHistory", { name: byKey.get(k)?.name ?? k })}</Link></li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
