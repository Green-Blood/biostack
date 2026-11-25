/**
 * Unit equivalence. A lab's tiers are only valid for results in the unit the lab printed them in
 * (25 ng/mL is not 25 nmol/L), so a tier is applied to a value only when the units are equivalent.
 * The alias map is deliberately small: it only folds spelling, case and Russian/English notation of the SAME unit.
 * It never converts between different units.
 */
const ALIASES: Record<string, string> = {
  нг: "ng", мкг: "ug", mcg: "ug", мг: "mg", г: "g", кг: "kg",
  мл: "ml", дл: "dl", л: "l",
  пмоль: "pmol", нмоль: "nmol", мкмоль: "umol", ммоль: "mmol", моль: "mol",
  ме: "iu", мме: "miu", мкме: "uiu", ед: "u", мед: "mu", мкед: "uu",
  мкм: "um", фл: "fl", пг: "pg", сек: "s", мин: "min",
};

export function canonicalUnit(unit: string | null | undefined): string {
  const compact = (unit ?? "").toLowerCase().replace(/\s+/g, "").replace(/[µμ]/g, "u").replace(/×/g, "x").replace(/\*/g, "^");
  return compact.split("/").map((part) => ALIASES[part] ?? part).join("/");
}

/** True when the two units name the same unit. An absent unit on either side is treated as compatible (older API). */
export function unitsCompatible(a: string | null | undefined, b: string | null | undefined): boolean {
  const ca = canonicalUnit(a), cb = canonicalUnit(b);
  return ca === "" || cb === "" || ca === cb;
}
