import type { Locale } from "./config";
import { dictionaries, type Dictionary } from "./dictionaries";

/** "namespace.key", checked against the English dictionary at compile time. */
export type Key = { [N in keyof Dictionary]: `${N & string}.${keyof Dictionary[N] & string}` }[keyof Dictionary];
export type Params = Record<string, string | number>;

type Flat = Record<string, string>;
const flat = (locale: Locale): Flat =>
  Object.fromEntries(Object.entries(dictionaries[locale]).flatMap(([ns, entries]) => Object.entries(entries as Flat).map(([k, v]) => [`${ns}.${k}`, v])));
const cache: Partial<Record<Locale, Flat>> = {};
const table = (locale: Locale) => (cache[locale] ??= flat(locale));

const fill = (text: string, params?: Params) => (params ? text.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`)) : text);

export function translate(locale: Locale, key: Key, params?: Params): string {
  return fill(table(locale)[key] ?? table("en")[key] ?? key, params);
}

/** Plural forms live in one string split by "|": "file|files" in English, "файл|файла|файлов" in Russian. */
export function translatePlural(locale: Locale, key: Key, n: number, params?: Params): string {
  const forms = (table(locale)[key] ?? table("en")[key] ?? key).split("|");
  const category = new Intl.PluralRules(locale).select(n);
  const index = locale === "ru" ? (category === "one" ? 0 : category === "few" ? 1 : 2) : category === "one" ? 0 : 1;
  return fill(forms[Math.min(index, forms.length - 1)], { n, ...params });
}

export type T = (key: Key, params?: Params) => string;
export type TPlural = (key: Key, n: number, params?: Params) => string;
