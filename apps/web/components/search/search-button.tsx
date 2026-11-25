"use client";
import { useSyncExternalStore } from "react";
import { Search } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import { OPEN_SEARCH_EVENT } from "./command-palette";

/** Sidebar trigger for the command palette; shows the platform's shortcut. */
export function SearchButton() {
  const { t } = useI18n();
  const mac = useSyncExternalStore(() => () => {}, () => /mac|iphone|ipad/i.test(navigator.platform), () => false);
  return (
    <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_SEARCH_EVENT))} aria-keyshortcuts="Control+K Meta+K"
      className="flex min-w-0 flex-1 items-center gap-2.5 rounded-full border border-border/70 bg-card/70 px-4 py-2.5 shadow-sm text-sm text-muted-foreground transition-colors hover:bg-card hover:shadow-md md:flex-none transition-[background-color,box-shadow] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <Search className="size-4" aria-hidden />
      <span className="flex-1 text-left">{t("search.open")}</span>
      <kbd className="hidden rounded border border-border px-1.5 text-[11px] font-sans md:inline">{mac ? t("search.openHintMac") : t("search.openHintOther")}</kbd>
    </button>
  );
}
