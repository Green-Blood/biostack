import { cookies } from "next/headers";
import { LOCALE_COOKIE, parseLocale } from "./config";
import { makeI18nFor, type ClientI18n } from "./client-core";

export type I18n = ClientI18n;

/** For server components: the language from the visitor's cookie. */
export async function getI18n(): Promise<I18n> {
  return makeI18nFor(parseLocale((await cookies()).get(LOCALE_COOKIE)?.value));
}
