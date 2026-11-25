import type { BodySnapshot, DiagnosisStatus, OrganIndex, OverviewMarker, Profile, RecordItem } from "@/lib/types";

export type Region =
  | "brain" | "eyes" | "thyroid" | "lungs" | "heart" | "liver" | "gallbladder" | "stomach" | "spleen" | "pancreas" | "kidneys"
  | "intestine" | "bladder" | "abdomen" | "spine" | "shoulders" | "elbows" | "hips" | "knees" | "ankles";
export const REGIONS: Region[] = ["brain", "eyes", "thyroid", "lungs", "heart", "liver", "gallbladder", "stomach", "spleen", "pancreas", "kidneys",
  "intestine", "bladder", "abdomen", "spine", "shoulders", "elbows", "hips", "knees", "ankles"];

/** high = diagnosis or very high index, warn = out of range or suspected, ok = measured and in range, info = scan history only. */
export type Level = "high" | "warn" | "ok" | "info";
export const RANK: Record<Level, number> = { high: 0, warn: 1, ok: 2, info: 3 };
export type Finding = { id: string; region: Region; level: Level; kind: "diagnosis" | "markers" | "visceral" | "waist" | "scan"; label: string; sub?: string; href: string };

// Free-text diagnosis name -> body region; the first match wins. Russian and English stems. No \b: it does not work with Cyrillic.
const RULES: [RegExp, Region][] = [
  [/щитовид|thyroid|тиреоид|гипотиреоз|гипертиреоз|hashimoto|(^|[^а-я])зоб|goit/i, "thyroid"],
  [/желчн|gallbladder|холецист|cholecyst|gallstone|cholelith|холестаз|билиар/i, "gallbladder"],
  [/поджелудоч|pancrea|панкреат|диабет|diabet/i, "pancreas"],
  [/печен|liver|гепат|hepat|стеатоз|steato|цирроз/i, "liver"],
  [/селез|spleen|спленомег/i, "spleen"],
  [/почк|kidney|renal|нефр|neph|мочекам/i, "kidneys"],
  [/мочев|bladder|цистит|cystit|простат|prostat/i, "bladder"],
  [/желуд|stomach|гастр|gastr|язв|ulcer|рефлюкс|reflux|gerd/i, "stomach"],
  [/кишеч|intestin|колит|colitis|крон|crohn|геморро|ibs|срк/i, "intestine"],
  [/легк|lung|бронх|bronch|астм|asthma|пневмон|pneum/i, "lungs"],
  [/сердц|heart|кардио|cardi|гипертон|гипертенз|артериальн|hypertens|аритм|arrhythm|ишеми|ischem|атеросклер|athero/i, "heart"],
  [/мозг|brain|мигрен|migrain|инсульт|stroke|эпилеп|epilep/i, "brain"],
  [/глаз|(^|[^a-z])eye|зрени|vision|катаракт|cataract|глауком|glaucoma|миопи|myopia/i, "eyes"],
  [/плеч|shoulder|ротатор/i, "shoulders"],
  [/локт|elbow|эпикондил|epicondyl/i, "elbows"],
  [/колен|knee|гонартроз|gonarthr|мениск|menisc/i, "knees"],
  [/голеностоп|ankle|ахилл|achilles|стопа|стопы|плоскостоп|(^|[^a-z])foot|подагр|gout/i, "ankles"],
  [/позвоно|spine|spinal|остеохондроз|грыж|hernia|сколиоз|scolios|остеопор|osteopor/i, "spine"],
  [/некроз|necrosis|тазобедр|(^|[^a-z])hip($|[^a-z])|коксартроз|coxarthr|остеоартр|osteoarthr/i, "hips"],
  [/ожирен|obes|висцеральн|visceral/i, "abdomen"],
];
export const regionOf = (name: string): Region | null => RULES.find(([re]) => re.test(name))?.[1] ?? null;

// Lab system (from /biomarkers) -> region. Systems without a single organ (blood count, vitamins...) stay off the map.
const SYSTEM_REGION: Record<string, Region> = { thyroid: "thyroid", liver: "liver", kidney: "kidneys", pancreas: "pancreas", glucose: "pancreas", lipids: "heart" };
const ORGAN_REGION: Record<string, Region> = { thyroid: "thyroid", liver: "liver", gallbladder: "gallbladder", pancreas: "pancreas", spleen: "spleen", kidneys: "kidneys", bladder: "bladder", prostate: "bladder" };

export const VISCERAL_WARN = 10;
export const VISCERAL_HIGH = 13;
export const WHTR_WARN = 0.5;

export type Labels = {
  systemName: (system: string) => string;
  markers: (system: string, out: number, total: number) => string;
  diagnosisSub: (status: DiagnosisStatus | null, title: string, date: string | null) => string;
  visceral: (v: string) => string; visceralSub: string;
  whtr: (v: string) => string; whtrSub: string;
  scan: (name: string, count: number) => string; scanSub: (headline: string | null, date: string | null) => string;
  num: (n: number, digits?: number) => string;
  unit: (u: string) => string;
};

/** Everything here is derived from stored data: diagnoses on records, latest lab results, scan history and the scale/profile. */
export function buildFindings(markers: OverviewMarker[], records: RecordItem[], body: BodySnapshot | null, profile: Profile | null, organs: OrganIndex | null, l: Labels): Finding[] {
  const out: Finding[] = [];
  const seen = new Set<string>();
  for (const r of records) {
    const items = r.diagnosis_items ?? (r.diagnoses ?? []).map((name) => ({ name, status: null as DiagnosisStatus | null }));
    for (const { name, status } of items) {
      const region = regionOf(name);
      if (!region || status === "ruled_out" || seen.has(`${region}|${name.toLowerCase()}`)) continue;
      seen.add(`${region}|${name.toLowerCase()}`);
      out.push({ id: `d${r.id}-${name}`, region, level: status === "suspected" ? "warn" : "high", kind: "diagnosis", label: name, sub: l.diagnosisSub(status, r.title, r.date), href: `/records/${r.id}` });
    }
  }
  const bySystem = new Map<string, OverviewMarker[]>();
  for (const m of markers) if (m.latest_value !== null && m.system && SYSTEM_REGION[m.system]) bySystem.set(m.system, [...(bySystem.get(m.system) ?? []), m]);
  for (const [system, items] of bySystem) {
    const bad = items.filter((m) => m.out_of_range_latest);
    out.push({ id: `m-${system}`, region: SYSTEM_REGION[system], level: bad.length > 0 ? "warn" : "ok", kind: "markers", label: l.markers(l.systemName(system), bad.length, items.length),
      sub: bad.map((m) => m.display_name).join(", ") || undefined,
      href: bad.length === 1 ? `/biomarkers/${encodeURIComponent(bad[0].marker_key)}` : `/biomarkers#${system}` });
  }
  for (const o of organs?.organs ?? []) {
    const region = ORGAN_REGION[o.key];
    if (!region || o.scan_count === 0) continue;
    const h = o.headline;
    out.push({ id: `s-${o.key}`, region, level: "info", kind: "scan", label: l.scan(o.name, o.scan_count),
      sub: l.scanSub(h ? `${h.name} ${l.num(h.value, 1)} ${l.unit(h.unit)}`.trim() : null, o.latest_date), href: `/organs/${encodeURIComponent(o.key)}` });
  }
  const v = body?.latest.visceral_fat?.value;
  if (v != null && v >= VISCERAL_WARN) out.push({ id: "visceral", region: "abdomen", level: v >= VISCERAL_HIGH ? "high" : "warn", kind: "visceral", label: l.visceral(l.num(v, 1)), sub: l.visceralSub, href: "/profile" });
  if (profile?.whtr != null && profile.whtr >= WHTR_WARN) out.push({ id: "whtr", region: "abdomen", level: "warn", kind: "waist", label: l.whtr(l.num(profile.whtr, 2)), sub: l.whtrSub, href: "/profile" });
  return out.sort((a, b) => RANK[a.level] - RANK[b.level]);
}
