"use client";
import { useEffect, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/client";

export type UnmappedItem = { raw_name: string; count: number; latest_value: number | null; latest_date: string; unit: string };
type CatalogMarker = { marker_key: string; display_name: string; system: string };

const slug = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_|_$/g, "");
const post = (path: string, body: unknown) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function UnmappedPanel({ items }: { items: UnmappedItem[] }) {
  const router = useRouter();
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<CatalogMarker[] | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState<Record<string, string | undefined>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!open || catalog) return;
    fetch("/api/labs/marker-catalog").then((r) => (r.ok ? r.json() : Promise.reject())).then(setCatalog).catch(() => setCatalog([]));
  }, [open, catalog]);

  if (items.length === 0 && !done) return null;
  const setError = (raw: string, msg?: string) => setErrors((e) => ({ ...e, [raw]: msg }));

  async function send(raw: string, path: string, body: unknown, success: (res: Response) => Promise<string>) {
    setBusy(raw); setError(raw, undefined);
    try {
      const res = await post(path, body);
      if (!res.ok) { setError(raw, await errorMessage(res, t("biomarkers.unmappedSaveFailed"))); return; }
      setDone(await success(res));
      router.refresh();
    } catch {
      setError(raw, t("biomarkers.unmappedSaveFailed"));
    } finally { setBusy(null); }
  }

  const match = (raw: string) => {
    const m = catalog?.find((c) => c.marker_key === picked[raw]);
    if (!m) { setError(raw, t("biomarkers.unmappedPickFirst")); return; }
    const count = items.find((i) => i.raw_name === raw)?.count ?? 0;
    // the API keeps the catalog's own (English) name for a catalog marker, so history stays canonical
    void send(raw, "/api/review/alias", { raw_name: raw, marker_key: m.marker_key, display_name: m.display_name },
      async () => tp("biomarkers.unmappedMatched", count, { name: raw, marker: m.display_name }));
  };
  const create = (raw: string) => {
    const display = (creating[raw] ?? "").trim();
    const key = slug(display);
    if (!key) { setError(raw, t("biomarkers.unmappedNameRequired")); return; }
    const count = items.find((i) => i.raw_name === raw)?.count ?? 0;
    void send(raw, "/api/review/alias", { raw_name: raw, marker_key: key, display_name: display },
      async () => tp("biomarkers.unmappedCreated", count, { marker: display }));
  };
  const hide = (raw: string) => void send(raw, "/api/review/ignore", { raw_name: raw }, async () => t("biomarkers.unmappedHidden", { name: raw }));

  return (
    <section className="surface min-w-0 border-l-4 border-l-warn p-4 sm:p-5">
      {items.length > 0 && (
        <div className="flex min-w-0 flex-wrap items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warn" aria-hidden />
          <div className="min-w-0 flex-1 basis-64">
            <h2 className="text-base font-semibold">{tp("biomarkers.unmappedTitle", items.length)}</h2>
            <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t("biomarkers.unmappedBody")}</p>
          </div>
          <Button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={listId}>
            {open ? t("biomarkers.unmappedClose") : t("biomarkers.unmappedReview", { n: items.length })}
          </Button>
        </div>
      )}
      <p role="status" className={done ? "mt-3 text-sm text-primary" : "sr-only"}>{done}</p>
      {open && items.length > 0 && (
        <ul id={listId} className="mt-4 space-y-3">
          {items.map((i) => {
            const raw = i.raw_name;
            const sel = `${listId}-sel-${raw}`;
            const isBusy = busy === raw;
            const latest = i.latest_value !== null
              ? t("biomarkers.unmappedLatest", { value: `${formatNumber(i.latest_value)}${i.unit ? " " + unit(i.unit) : ""}`, date: formatDate(i.latest_date) })
              : t("biomarkers.unmappedLatestText", { date: formatDate(i.latest_date) });
            return (
              <li key={raw} className="min-w-0 space-y-3 rounded-2xl border border-border/70 bg-card/60 p-3">
                <div className="min-w-0">
                  <p className="break-words font-medium">{raw}</p>
                  <p className="text-xs text-muted-foreground">{tp("biomarkers.unmappedResults", i.count)} · {latest}</p>
                </div>
                <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
                  <select id={sel} aria-label={t("biomarkers.unmappedMatchLabel", { name: raw })} value={picked[raw] ?? ""} disabled={isBusy}
                    onChange={(e) => setPicked({ ...picked, [raw]: e.target.value })}
                    className="h-10 w-full min-w-0 rounded-xl border border-input bg-card/60 px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 sm:flex-1">
                    <option value="">{t("biomarkers.unmappedMatchPlaceholder")}</option>
                    {(catalog ?? []).map((c) => <option key={c.marker_key} value={c.marker_key}>{c.display_name}</option>)}
                  </select>
                  <Button type="button" onClick={() => match(raw)} disabled={isBusy || !catalog}>{t("biomarkers.unmappedMatch")}</Button>
                </div>
                {creating[raw] !== undefined && (
                  <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
                    <Input value={creating[raw]} placeholder={t("biomarkers.unmappedCreatePlaceholder")} aria-label={t("biomarkers.unmappedCreateLabel", { name: raw })}
                      onChange={(e) => setCreating({ ...creating, [raw]: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") create(raw); }} className="sm:flex-1" />
                    <div className="flex gap-2">
                      <Button type="button" onClick={() => create(raw)} disabled={isBusy}>{t("biomarkers.unmappedCreate")}</Button>
                      <Button type="button" variant="ghost" onClick={() => setCreating({ ...creating, [raw]: undefined })}>{t("biomarkers.unmappedCancel")}</Button>
                    </div>
                  </div>
                )}
                <div className="flex min-w-0 flex-wrap gap-2">
                  {creating[raw] === undefined && (
                    <Button type="button" size="sm" variant="outline" onClick={() => setCreating({ ...creating, [raw]: "" })}>{t("biomarkers.unmappedCreateOpen")}</Button>
                  )}
                  <Button type="button" size="sm" variant="outline" disabled={isBusy} onClick={() => hide(raw)} aria-label={t("biomarkers.unmappedIgnoreLabel", { name: raw })}>{t("biomarkers.unmappedIgnore")}</Button>
                </div>
                {errors[raw] && <p role="alert" className="text-sm text-outrange">{errors[raw]}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
