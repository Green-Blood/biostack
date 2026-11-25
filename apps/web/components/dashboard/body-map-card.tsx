import Link from "next/link";
import { ScanLine } from "lucide-react";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { Key } from "@/lib/i18n/translate";
import type { BodyKind, BodySnapshot, OrganIndex, OverviewMarker, Profile, RecordItem } from "@/lib/types";
import { KINDS } from "@/components/profile/body-kinds";
import { BodyMap } from "./body-map";
import { buildFindings, REGIONS, type Level, type Region } from "./body-map-model";
import { RingGauge, type Verdict } from "./ring-gauge";

type Sex = "male" | "female";
type Band = { male: [number, number]; female: [number, number] };
// Rough adult reference bands used by consumer scales. Bone mass has no band, so it is shown without a verdict.
const RINGS: { kind: BodyKind; name: "water" | "fat" | "protein" | "bone"; unit: string; band: Band | null; max: number }[] = [
  { kind: "body_water_pct", name: "water", unit: "%", band: { male: [50, 65], female: [45, 60] }, max: 80 },
  { kind: "body_fat_pct", name: "fat", unit: "%", band: { male: [10, 20], female: [18, 28] }, max: 45 },
  { kind: "protein_pct", name: "protein", unit: "%", band: { male: [16, 20], female: [14, 18] }, max: 30 },
  { kind: "bone_kg", name: "bone", unit: "kg", band: null, max: 6 },
];
const TILES: BodyKind[] = ["muscle_kg", "skeletal_muscle_kg", "fat_mass_kg", "lean_mass_kg", "bmr_kcal", "body_age", "waist", "hip"];
// Body type grid: columns by body fat, rows by BMI (top = high). BMI cut-offs 18.5 and 24.9.
const FAT_CUT: Record<Sex, [number, number]> = { male: [11, 17], female: [20, 27] };
const GRID = [["athlete", "muscularObesity", "obesity"], ["muscular", "healthy", "hidden"], ["emaciated", "slim", "slimFat"]] as const;
const BAD = new Set(["obesity", "hidden", "slimFat", "muscularObesity"]);

export async function BodyMapCard({ markers, records, profile }: { markers: OverviewMarker[]; records: RecordItem[]; profile: Profile | null }) {
  const { t, formatNumber, formatDate, unit } = await getI18n();
  const [body, organs] = await Promise.all([
    apiGet<BodySnapshot>("profile/body").catch(() => null), apiGet<OrganIndex>("organs").catch(() => null),
  ]);
  const num = (n: number, digits = 1) => formatNumber(n, { maximumFractionDigits: digits });
  const k = (key: string) => `bodyMap.${key}` as Key;

  const findings = buildFindings(markers, records, body, profile, organs, {
    systemName: (s) => t(k(`sys_${s}`)),
    markers: (system, out, total) => (out > 0 ? t(k("markersOut"), { system, out, total }) : t(k("markersOk"), { system, total })),
    diagnosisSub: (status, title, date) => [status ? t(k(`dx_${status}`)) : null, title, date ? formatDate(date, { day: "numeric", month: "short", year: "numeric" }) : null].filter(Boolean).join(" · "),
    visceral: (v) => t(k("visceral"), { value: v }), visceralSub: t(k("visceralSub")),
    whtr: (v) => t(k("whtr"), { value: v }), whtrSub: t(k("whtrSub")),
    scan: (name, count) => t(k("scan"), { name, count }),
    scanSub: (headline, date) => [headline, date ? t(k("scanLatest"), { date: formatDate(date, { day: "numeric", month: "short", year: "numeric" }) }) : null].filter(Boolean).join(" · "),
    num,
    unit,
  });
  const names = Object.fromEntries(REGIONS.map((r) => [r, t(k(`r_${r}`))])) as Record<Region, string>;
  const where = Object.fromEntries(REGIONS.map((r) => [r, t(k(`d_${r}`))])) as Record<Region, string>;
  const levelNames = Object.fromEntries((["high", "warn", "ok", "info"] as Level[]).map((l) => [l, t(k(`lvl_${l}`))])) as Record<Level, string>;

  const latest = body?.latest ?? {};
  const sex: Sex = profile?.sex === "female" ? "female" : "male";
  const rings = RINGS.filter((r) => latest[r.kind]).map((r) => {
    const v = latest[r.kind]!.value, band = r.band?.[sex] ?? null;
    const verdict: Verdict = band ? (v < band[0] ? "low" : v > band[1] ? "high" : "ok") : null;
    return <RingGauge key={r.kind} value={v} text={num(v)} unit={unit(r.unit)} max={r.max} range={band} label={t(k(`c_${r.name}`))} verdict={verdict} verdictLabel={verdict ? t(k(`v_${verdict}`)) : null} />;
  });
  const vis = latest.visceral_fat?.value;
  if (vis != null) {
    const verdict: Verdict = vis >= 13 ? "high" : vis >= 10 ? "warn" : "ok";
    rings.push(<RingGauge key="visceral" value={vis} text={num(vis)} unit="" max={30} range={[1, 9]} label={t("profile.kindVisceral")} verdict={verdict} verdictLabel={t(k(`v_${verdict}`))} />);
  }
  const tiles = TILES.filter((kind) => latest[kind]).map((kind) => {
    const meta = KINDS.find((x) => x.kind === kind)!;
    return { kind, label: t(meta.label), value: formatNumber(latest[kind]!.value, { maximumFractionDigits: meta.digits }), unit: unit(meta.unit) };
  });

  const fat = latest.body_fat_pct?.value, bmi = profile?.bmi?.value;
  let cell: [number, number] | null = null;
  if (fat != null && bmi != null) {
    const [a, b] = FAT_CUT[sex];
    cell = [bmi >= 24.9 ? 0 : bmi >= 18.5 ? 1 : 2, fat < a ? 0 : fat < b ? 1 : 2];
  }

  const side = (rings.length > 0 || tiles.length > 0) ? (
    <div className="holo-panel grid gap-x-8 gap-y-4 p-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-start">
      <div className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-300">{t(k("compTitle"))}</h3>
        {rings.length > 0 && <div className="grid grid-cols-3 gap-x-2 gap-y-4 sm:grid-cols-5">{rings}</div>}
        {rings.length > 0 && <p className="text-[11px] leading-snug text-[#8fb0d6]"><span className="mr-1 inline-block h-1.5 w-3 rounded-full bg-[#34d399]/50 align-middle" aria-hidden />{t(k("compSub"))}</p>}
      </div>
      {tiles.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-t border-cyan-400/15 pt-3 sm:grid-cols-4 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          {tiles.map((x) => (
            <div key={x.kind} className="min-w-0"><dt className="text-[11px] leading-tight text-[#8fb0d6]">{x.label}</dt><dd className="mt-0.5 text-sm font-semibold text-white tnum">{x.value} <span className="text-xs font-normal text-[#8fb0d6]">{x.unit}</span></dd></div>
          ))}
        </dl>
      )}
    </div>
  ) : null;

  return (
    <section aria-labelledby="body-h" className="holo space-y-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <div>
          <h2 id="body-h" className="flex items-center gap-2 !text-white"><ScanLine className="size-5 text-cyan-300" aria-hidden />{t(k("title"))}</h2>
          <p className="mt-0.5 text-sm text-[#8fb0d6]">{t(k("sub"))}</p>
        </div>
        <Link href="/organs" className="text-sm text-cyan-300 underline-offset-4 hover:underline">{t(k("allOrgans"))}</Link>
      </header>
      <BodyMap findings={findings} names={names} where={where} levelNames={levelNames} layerNames={{ organs: t(k("layerOrgans")), skeleton: t(k("layerSkeleton")) }}
        label={t(k("title"))} openLabel={t(k("open"))} emptyLabel={t(k("empty"))} whereLabel={t(k("whereLabel"))} side={side} />
      {cell && (
        <div className="holo-panel grid items-center gap-4 p-4 sm:grid-cols-[minmax(0,360px)_1fr]">
          <div className="grid grid-cols-3 gap-1.5" role="img" aria-label={t(k(`b_${GRID[cell[0]][cell[1]]}`))}>
            {GRID.flatMap((row, r) => row.map((name, c) => {
              const on = cell![0] === r && cell![1] === c, color = BAD.has(name) ? "#ff4d6d" : "#34d399";
              return (
                <div key={`${r}${c}`} className="flex min-h-14 items-center justify-center rounded-lg border p-1 text-center text-[11px] leading-tight sm:text-xs"
                  style={on ? { borderColor: color, color, background: `${color}22`, boxShadow: `0 0 14px ${color}55`, fontWeight: 600 } : { borderColor: "rgba(56,189,248,.18)", color: "#6d8bb0" }}>
                  {t(k(`b_${name}`))}
                </div>
              );
            }))}
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-300">{t(k("typeTitle"))}</h3>
            <p className="text-2xl font-semibold text-white">{t(k(`b_${GRID[cell[0]][cell[1]]}`))}</p>
            <p className="text-sm text-[#8fb0d6] tnum">{t(k("typeSub"), { fat: num(fat!), bmi: num(bmi!) })} · {t(k("typeCuts"), { a: FAT_CUT[sex][0], b: FAT_CUT[sex][1] })}</p>
            <Link href="/profile" className="inline-block pt-1 text-sm text-cyan-300 underline-offset-4 hover:underline">{t(k("open"))}</Link>
          </div>
        </div>
      )}
    </section>
  );
}
