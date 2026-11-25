import Link from "next/link";
import type { OverviewMarker } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import type { Key } from "@/lib/i18n/translate";
import { SectionHeader } from "./section-header";

const SYSTEMS: Record<string, Key> = {
  thyroid: "common.systemThyroid", liver: "common.systemLiver", lipids: "common.systemLipids", blood_count: "common.systemBloodCount",
  minerals: "common.systemMinerals", inflammation: "common.systemInflammation", hormones: "common.systemHormones", vitamins: "common.systemVitamins",
  glucose: "common.systemGlucose", coagulation: "common.systemCoagulation", kidney: "common.systemKidney", pancreas: "common.systemPancreas", other: "common.systemOther",
};
const ORDER = Object.keys(SYSTEMS);

type Status = "out" | "stale" | "ok";
const status = (m: OverviewMarker): Status =>
  m.out_of_range_latest ? "out" : m.retest_days != null && m.age_days != null && m.age_days > m.retest_days ? "stale" : "ok";
const DOT: Record<Status, string> = { out: "bg-outrange", stale: "bg-warn", ok: "bg-ok" };
const RANK: Record<Status, number> = { out: 0, stale: 1, ok: 2 };

/** One tile per body system that has data. Renders nothing when the API does not provide `system` yet. */
export async function SystemsGrid({ markers }: { markers: OverviewMarker[] }) {
  const { t, tp } = await getI18n();
  const groups = new Map<string, OverviewMarker[]>();
  for (const m of markers) if (m.system && SYSTEMS[m.system]) groups.set(m.system, [...(groups.get(m.system) ?? []), m]);
  if (groups.size === 0) return null;
  const keys = ORDER.filter((k) => groups.has(k));

  return (
    <section aria-labelledby="sys-h">
      <SectionHeader id="sys-h" title={t("overview.systemsHeading")} sub={t("overview.systemsSub")} />
      <ul className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {keys.map((k) => {
          const items = groups.get(k)!;
          const sts = items.map(status).sort((a, b) => RANK[a] - RANK[b]);
          const ok = items.filter((m) => !m.out_of_range_latest).length;
          const stale = sts.filter((s) => s === "stale").length;
          return (
            <li key={k}>
              <Link href={`/biomarkers#${k}`} className="surface surface-interactive block h-full p-4">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-medium leading-snug">{t(SYSTEMS[k])}</span>
                  <span className={`tnum text-sm font-semibold ${ok < items.length ? "text-outrange" : "text-ok"}`}>{ok}/{items.length}</span>
                </span>
                <span className="mt-1 block text-sm text-muted-foreground tnum">{t("overview.systemTile", { ok, total: items.length })}{stale > 0 && <> · {tp("overview.systemStale", stale)}</>}</span>
                <span className="mt-3 flex flex-wrap gap-1" aria-hidden>
                  {sts.map((s, i) => <span key={i} className={`size-2.5 rounded-full ${DOT[s]}`} />)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
