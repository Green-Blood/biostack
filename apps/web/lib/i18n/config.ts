export const LOCALES = ["en", "ru"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "biostack_lang";

export function parseLocale(value: string | undefined | null): Locale {
  return (LOCALES as readonly string[]).includes(value ?? "") ? (value as Locale) : DEFAULT_LOCALE;
}
