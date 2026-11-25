"use client";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { Locale } from "./config";
import { makeI18nFor, type ClientI18n } from "./client-core";

const Context = createContext<ClientI18n | null>(null);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const value = useMemo(() => makeI18nFor(locale), [locale]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** For client components: translate and format in the current language. */
export function useI18n(): ClientI18n {
  const value = useContext(Context);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
