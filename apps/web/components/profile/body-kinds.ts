import type { Key } from "@/lib/i18n/translate";
import type { BodyKind, BodyMeasurement, BodyPoint, BodySnapshot } from "@/lib/types";

export type KindMeta = { kind: BodyKind; label: Key; unit: string; digits: number };

/** Every kind a measurement can have, in display order. Units are canonical (English); unit() localises them. */
export const KINDS: KindMeta[] = [
  { kind: "weight", label: "profile.kindWeight", unit: "kg", digits: 1 },
  { kind: "waist", label: "profile.kindWaist", unit: "cm", digits: 1 },
  { kind: "body_fat_pct", label: "profile.kindBodyFat", unit: "%", digits: 1 },
  { kind: "muscle_kg", label: "profile.kindMuscle", unit: "kg", digits: 1 },
  { kind: "body_water_pct", label: "profile.kindWater", unit: "%", digits: 1 },
  { kind: "bone_kg", label: "profile.kindBone", unit: "kg", digits: 2 },
  { kind: "visceral_fat", label: "profile.kindVisceral", unit: "index", digits: 1 },
  { kind: "bmr_kcal", label: "profile.kindBmr", unit: "kcal", digits: 0 },
  { kind: "skeletal_muscle_kg", label: "profile.kindSkeletalMuscle", unit: "kg", digits: 1 },
  { kind: "skeletal_muscle_pct", label: "profile.kindSkeletalMusclePct", unit: "%", digits: 1 },
  { kind: "protein_pct", label: "profile.kindProtein", unit: "%", digits: 1 },
  { kind: "body_age", label: "profile.kindBodyAge", unit: "years", digits: 0 },
  { kind: "hip", label: "profile.kindHip", unit: "cm", digits: 1 },
  { kind: "fat_mass_kg", label: "profile.kindFatMassKg", unit: "kg", digits: 1 },
  { kind: "lean_mass_kg", label: "profile.kindLeanMassKg", unit: "kg", digits: 1 },
  { kind: "active_cell_mass_kg", label: "profile.kindActiveCellMassKg", unit: "kg", digits: 1 },
  { kind: "active_cell_mass_pct", label: "profile.kindActiveCellMassPct", unit: "%", digits: 1 },
  { kind: "total_body_water_kg", label: "profile.kindTotalBodyWaterKg", unit: "kg", digits: 1 },
  { kind: "extracellular_water_kg", label: "profile.kindExtracellularWaterKg", unit: "kg", digits: 1 },
  { kind: "ecw_icw_ratio", label: "profile.kindEcwIcwRatio", unit: "ratio", digits: 2 },
  { kind: "phase_angle", label: "profile.kindPhaseAngle", unit: "°", digits: 1 },
  { kind: "specific_bmr", label: "profile.kindSpecificBmr", unit: "kcal/m²/day", digits: 1 },
];
export const COMPOSITION: KindMeta[] = KINDS.slice(2);
export const metaOf = (kind: BodyKind): KindMeta => KINDS.find((k) => k.kind === kind) ?? KINDS[0];

/** Latest and previous reading per kind: the API's snapshot when it has one, otherwise worked out from the list. */
export function snapshotOf(body: BodySnapshot | null, rows: BodyMeasurement[]): BodySnapshot {
  if (body) return body;
  const latest: Partial<Record<BodyKind, BodyPoint>> = {}, previous: Partial<Record<BodyKind, BodyPoint>> = {};
  for (const m of [...rows].sort((a, b) => b.date.localeCompare(a.date))) {
    if (!latest[m.kind]) latest[m.kind] = { date: m.date, value: m.value };
    else if (!previous[m.kind]) previous[m.kind] = { date: m.date, value: m.value };
  }
  return { latest, previous };
}
