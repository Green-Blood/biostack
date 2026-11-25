"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { getJson, sendJson } from "@/lib/request";
import type { MarkerSummaryFull, NeedsProfile, Profile } from "@/lib/types";

const covered = (needs: NeedsProfile, p: Profile) => (needs === "sex" ? !!p.sex : needs === "age" ? !!p.birth_date : !!p.sex && !!p.birth_date);

/** Offers to fill ranges of saved results that were blank only because the profile lacked sex or age. */
export function RefillCard({ profile }: { profile: Profile }) {
  const { t, formatNumber } = useI18n();
  const [needs, setNeeds] = useState<(NeedsProfile | null | undefined)[]>([]);
  const [busy, setBusy] = useState(false);
  const [filled, setFilled] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let live = true;
    getJson<MarkerSummaryFull[]>("biomarkers").then((all) => { if (live) setNeeds(all.map((m) => m.needs_profile)); }, () => { if (live) setNeeds([]); });
    return () => { live = false; };
  }, [version]);

  const eligible = needs.some((n) => n && covered(n, profile));
  if (!eligible && filled === null) return null;

  async function run() {
    setBusy(true); setError(null);
    try {
      const res = await sendJson<{ filled: number }>("profile/refill-ranges", "POST");
      setFilled(res?.filled ?? 0);
      setVersion((v) => v + 1);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <section aria-labelledby="refill-h" className="surface min-w-0 space-y-3 p-4 sm:p-5 lg:col-span-2">
      <h2 id="refill-h" className="text-2xl font-semibold">{t("profile.refillTitle")}</h2>
      <p className="max-w-prose text-sm text-muted-foreground">{t("profile.refillIntro")}</p>
      <div className="flex flex-wrap items-center gap-3">
        {eligible && <Button type="button" variant="outline" disabled={busy} onClick={() => void run()}>{busy ? t("profile.refilling") : t("profile.refillBtn")}</Button>}
        {filled !== null && <p role="status" className="text-sm font-medium">{filled > 0 ? t("profile.refillDone", { n: formatNumber(filled) }) : t("profile.refillNothing")}</p>}
      </div>
      {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
      <p className="max-w-prose text-xs text-muted-foreground">{t("profile.refillNote")}</p>
    </section>
  );
}
