import type { Key } from "@/lib/i18n/translate";
import type { BmiCategory } from "@/lib/types";

export const CATEGORY_KEY: Record<BmiCategory, Key> = {
  underweight: "profile.catUnderweight", normal: "profile.catNormal", overweight: "profile.catOverweight",
  obese_1: "profile.catObese1", obese_2: "profile.catObese2", obese_3: "profile.catObese3",
};

/** Decimal comma or point; blank is null, anything else NaN. */
export const parseDecimal = (s: string): number | null => {
  const t = s.trim().replace(",", ".");
  return t === "" ? null : Number(t);
};
