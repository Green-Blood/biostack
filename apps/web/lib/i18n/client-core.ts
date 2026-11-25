import type { Locale } from "./config";
import { formatDate, formatNumber, formatTime, formatUnit } from "./format";
import { translate, translatePlural, type T, type TPlural } from "./translate";

export type ClientI18n = { locale: Locale; t: T; tp: TPlural; formatDate: (iso: string, o?: Intl.DateTimeFormatOptions) => string; formatNumber: (n: number, o?: Intl.NumberFormatOptions) => string; formatTime: (iso: string) => string; unit: (u: string) => string };

export function makeI18nFor(locale: Locale): ClientI18n {
  return {
    locale,
    t: (key, params) => translate(locale, key, params),
    tp: (key, n, params) => translatePlural(locale, key, n, params),
    formatDate: (iso, o) => formatDate(locale, iso, o),
    formatNumber: (n, o) => formatNumber(locale, n, o),
    formatTime: (iso) => formatTime(locale, iso),
    unit: (u) => formatUnit(locale, u),
  };
}
