"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { BedtimeReadout, Preset, SupplementLog } from "@/lib/types";

type Props = { presets: Preset[]; initialRecent: SupplementLog[]; initialBedtime: BedtimeReadout };
type Toast = { logId: number; text: string };

const TOAST_MS = 8000;
const label = (p: { item_name: string; dosage: number | null; unit: string }) => [p.item_name, p.dosage ?? "", p.unit].filter((part) => part !== "").join(" ");

export function QuickSupplements({ presets, initialRecent, initialBedtime }: Props) {
  const { t, formatNumber, formatTime } = useI18n();
  const [recent, setRecent] = useState(initialRecent);
  const [bedtime, setBedtime] = useState(initialBedtime);
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function reload() {
    const [logs, readout] = await Promise.all([getJson<SupplementLog[]>("supplements?days=1"), getJson<BedtimeReadout>("supplements/bedtime")]);
    setRecent(logs); setBedtime(readout);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); await reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const log = (preset: Preset) => run(async () => {
    const saved = await sendJson<SupplementLog>("supplements/quick", "POST", { ...preset });
    setToast({ logId: saved.id, text: t("journal.logged", { name: label(preset) }) });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), TOAST_MS);
  });
  const undo = (target: Toast) => run(async () => { await sendJson(`supplements/${target.logId}`, "DELETE"); setToast({ logId: -1, text: t("journal.logRemoved") }); });

  const caffeine = bedtime.items.find((i) => i.item_name.toLowerCase() === "caffeine");
  return (
    <section aria-labelledby="supplements-title" className="space-y-5">
      <h2 id="supplements-title" className="font-semibold">{t("journal.supplementsTitle")}</h2>
      <div className="rounded-xl border bg-card p-5">
        <p className="text-sm text-muted-foreground">{t("journal.caffeineAt", { time: bedtime.bedtime })}</p>
        <p className="font-heading tnum mt-1 text-5xl font-semibold tracking-tight" aria-live="polite">
          {caffeine ? <>{formatNumber(Math.round(caffeine.remaining))}<span className="ml-1.5 text-xl font-normal text-muted-foreground">{caffeine.unit || t("journal.mg")}</span></> : t("journal.none")}
        </p>
        {!caffeine && <p className="mt-1 text-sm text-muted-foreground">{t("journal.noCaffeine")}</p>}
      </div>
      {presets.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-5 text-sm text-muted-foreground">{t("journal.noPresets")} <Link href="/settings" className="underline underline-offset-4">{t("journal.addPresets")}</Link> {t("journal.noPresetsTail")}</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label={t("journal.quickAria")}>
          {presets.map((p) => (
            <li key={p.item_name}><Button variant="outline" size="lg" disabled={busy} onClick={() => log(p)}>{label(p)}</Button></li>
          ))}
        </ul>
      )}
      <div aria-live="polite" className="min-h-9">
        {toast && (
          <p role="status" className="flex flex-wrap items-center gap-3 text-sm">
            {toast.text}
            {toast.logId > 0 && <Button size="sm" variant="outline" disabled={busy} onClick={() => undo(toast)}>{t("journal.undo")}</Button>}
          </p>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
      {recent.length > 0 && (
        <div>
          <h3 className="text-lg">{t("journal.last24")}</h3>
          <ul className="mt-2 divide-y text-sm">
            {recent.map((r) => (
              <li key={r.id} className="flex items-baseline justify-between gap-4 py-2"><span>{label(r)}</span><span className="tnum text-muted-foreground">{formatTime(r.timestamp)}</span></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
