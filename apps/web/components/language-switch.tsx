"use client";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { setLocale } from "@/app/actions/set-locale";
import { LOCALES, type Locale } from "@/lib/i18n/config";
import { useI18n } from "@/lib/i18n/client";

const LABEL: Record<Locale, string> = { ru: "Русский", en: "English" };

export function LanguageSwitch() {
  const router = useRouter();
  const { locale, t } = useI18n();

  const [pending, startTransition] = useTransition();

  function choose(next: Locale) {
    if (next === locale) return;
    startTransition(async () => {
      await setLocale(next);
      router.refresh();
    });
  }

  return (
    <div role="group" aria-label={t("nav.language")} className="flex gap-1 text-sm">
      {LOCALES.map((code) => (
        <button key={code} type="button" onClick={() => choose(code)} aria-pressed={code === locale} lang={code} disabled={pending}
          className={`rounded-full px-3 py-1.5 transition-colors hover:bg-sidebar-accent ${code === locale ? "bg-sidebar-accent font-medium" : "text-muted-foreground"}`}>
          {LABEL[code]}
        </button>
      ))}
    </div>
  );
}
