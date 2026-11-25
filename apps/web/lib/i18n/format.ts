import type { Locale } from "./config";

const TAG: Record<Locale, string> = { ru: "ru-RU", en: "en-GB" };

export function formatNumber(locale: Locale, value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(TAG[locale], { maximumFractionDigits: 2, ...options }).format(value);
}

/** Dates arrive from the API as plain YYYY-MM-DD; read them as local calendar dates, never shifted by a time zone. */
export function parseDay(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function formatDate(locale: Locale, iso: string, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }): string {
  return new Intl.DateTimeFormat(TAG[locale], options).format(parseDay(iso));
}

/** Clock time (HH:MM) of an ISO timestamp, in this computer's time zone. */
export function formatTime(locale: Locale, iso: string): string {
  return new Intl.DateTimeFormat(TAG[locale], { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

// Units are stored in one canonical (English) spelling; Russian readers expect the Cyrillic notation.
const UNITS_RU: Record<string, string> = {
  "IU/ml": "МЕ/мл", "IU/mL": "МЕ/мл", "IU/L": "МЕ/л", "U/L": "Ед/л", "mU/L": "мЕд/л", "mIU/L": "мМЕ/л", "мME/л": "мМЕ/л",
  "µIU/mL": "мкМЕ/мл", "g/L": "г/л", "g/dL": "г/дл", "mg/L": "мг/л", "mg/dL": "мг/дл", "µg/dL": "мкг/дл",
  "ng/mL": "нг/мл", "ng/dL": "нг/дл", "pg/mL": "пг/мл", "pg": "пг", "pmol/L": "пмоль/л", "nmol/L": "нмоль/л",
  "mmol/L": "ммоль/л", "µmol/L": "мкмоль/л", "mEq/L": "мэкв/л", "mm/h": "мм/ч", "fL": "фл",
  "kg": "кг", "kcal": "ккал", "years": "лет", "ratio": "отн.", "kcal/m²/day": "ккал/м²/сут", "index": "ед.", "kg/m²": "кг/м²", "cm": "см", "mm": "мм", "cm³": "см³", "mL": "мл", "ml": "мл",
  "10^9/L": "×10⁹/л", "10^12/L": "×10¹²/л",
};

export function formatUnit(locale: Locale, unit: string): string {
  return locale === "ru" ? (UNITS_RU[unit] ?? unit) : unit;
}
