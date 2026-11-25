"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { LanguageSwitch } from "@/components/language-switch";
import { SearchButton } from "@/components/search/search-button";
import { ThemePicker } from "@/components/theme-picker";
import { Sheet } from "@/components/sheet";
import type { ThemeId } from "@/lib/theme";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { Activity, BookOpen, ClipboardList, FilePlus, HeartPulse, Home, Lock, Network, ListTree, ScanLine, Settings, Sparkles, Stethoscope, UserRound } from "lucide-react";

const NAV: { href: string; label: Key; icon: typeof Home }[] = [
  { href: "/", label: "nav.overview", icon: Home },
  { href: "/timeline", label: "nav.timeline", icon: ListTree },
  { href: "/biomarkers", label: "nav.biomarkers", icon: Activity },
  { href: "/organs", label: "nav.organs", icon: Stethoscope },
  { href: "/signals", label: "nav.signals", icon: HeartPulse },
  { href: "/graph", label: "nav.graph", icon: Network },
  { href: "/imaging", label: "nav.imaging", icon: ScanLine },
  { href: "/labs/new", label: "nav.addResults", icon: FilePlus },
  { href: "/journal", label: "nav.journal", icon: BookOpen },
  { href: "/ask", label: "nav.ask", icon: Sparkles },
  { href: "/doctor", label: "nav.doctor", icon: ClipboardList },
  { href: "/profile", label: "nav.profile", icon: UserRound },
  { href: "/settings", label: "nav.settings", icon: Settings },
];

export function Sidebar({ theme, passwordEnabled = false }: { theme: ThemeId; passwordEnabled?: boolean }) {
  const path = usePathname();
  const { t } = useI18n();

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.reload();
  }

  return (
    <>
      {/* Compact top bar on mobile: logo + search + menu. Desktop keeps the full sidebar. */}
      <header className="flex items-center gap-2 border-b bg-sidebar px-4 py-2.5 md:hidden">
        <Link href="/" className="flex items-center gap-2 font-heading text-xl font-semibold tracking-tight">
          <span aria-hidden className="size-2.5 rounded-full bg-[linear-gradient(135deg,var(--primary),var(--chart-4))]" />
          BioStack
        </Link>
        <div className="min-w-0 flex-1"><SearchButton /></div>
        <Sheet trigger={<Menu className="size-5" aria-hidden />} label={t("nav.main")} side="bottom"
          footer={
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.theme")}</p>
                <ThemePicker current={theme} variant="rows" />
              </div>
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.language")}</p>
                <LanguageSwitch />
              </div>
            </div>
          }
        >
          <nav className="flex flex-col gap-5">
            <div className="space-y-1.5">
              <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.sectionView")}</p>
              <div className="flex flex-col gap-1">
                {NAV.slice(0, 7).map(({ href, label, icon: Icon }) => {
                  const active = href === "/" ? path === "/" : path.startsWith(href);
                  return (
                    <Link key={href} href={href} aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-3 rounded-2xl px-3 py-3 text-base ${active ? "bg-primary/12 font-medium text-primary" : "text-foreground hover:bg-sidebar-accent"}`}>
                      <Icon className="size-5" aria-hidden /> {t(label)}
                    </Link>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.sectionActions")}</p>
              <div className="flex flex-wrap gap-2">
                {NAV.slice(7, 11).map(({ href, label, icon: Icon }) => {
                  const active = href === "/" ? path === "/" : path.startsWith(href);
                  return (
                    <Link key={href} href={href} aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2 rounded-2xl border px-3 py-2.5 text-sm ${active ? "border-primary bg-primary/10 font-medium text-primary" : "border-border text-foreground hover:bg-sidebar-accent"}`}>
                      <Icon className="size-4" aria-hidden /> {t(label)}
                    </Link>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.sectionAccount")}</p>
              <div className="flex flex-wrap gap-2">
                {NAV.slice(11).map(({ href, label, icon: Icon }) => {
                  const active = href === "/" ? path === "/" : path.startsWith(href);
                  return (
                    <Link key={href} href={href} aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2 rounded-2xl border px-3 py-2.5 text-sm ${active ? "border-primary bg-primary/10 font-medium text-primary" : "border-border text-foreground hover:bg-sidebar-accent"}`}>
                      <Icon className="size-4" aria-hidden /> {t(label)}
                    </Link>
                  );
                })}
              </div>
            </div>
          </nav>
        </Sheet>
      </header>

      <aside className="hidden border-r bg-sidebar md:flex md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:overflow-y-auto">
        <div className="flex min-h-full w-full flex-col gap-5 px-5 py-6">
          <Link href="/" className="flex items-center gap-2 font-heading text-2xl font-semibold tracking-tight">
            <span aria-hidden className="size-3 rounded-full bg-[linear-gradient(135deg,var(--primary),var(--chart-4))] shadow-[0_0_14px_color-mix(in_oklab,var(--primary)_55%,transparent)]" />
            BioStack
          </Link>
          <SearchButton />
          <nav aria-label={t("nav.main")} className="flex flex-col gap-1">
            {NAV.map(({ href, label, icon: Icon }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link key={href} href={href} aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-full px-4 py-2 text-sm transition-[background-color,color,transform] duration-200 ease-[var(--ease-out)] hover:bg-sidebar-accent hover:text-foreground active:scale-[0.97] ${active ? "bg-primary/12 font-medium text-primary" : "text-muted-foreground"}`}>
                  <Icon className="size-4" aria-hidden /> {t(label)}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("nav.theme")}</p>
              <ThemePicker current={theme} variant="dots" />
            </div>
            <LanguageSwitch />
            {passwordEnabled && (
              <button type="button" onClick={signOut} className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
                <Lock className="size-3.5" aria-hidden /> {t("nav.signOut")}
              </button>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}