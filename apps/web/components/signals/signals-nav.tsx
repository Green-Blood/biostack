import Link from "next/link";
import { cn } from "cn";
import { getI18n } from "@/lib/i18n/server";
import type { Key } from "@/lib/i18n/translate";

export type SignalsPage = "overview" | "sleep" | "heart" | "activity";
const PAGES: { page: SignalsPage; href: string; key: Key }[] = [
  { page: "overview", href: "/signals", key: "heart.navOverview" },
  { page: "sleep", href: "/signals/sleep", key: "heart.navSleep" },
  { page: "heart", href: "/signals/heart", key: "heart.navHeart" },
  { page: "activity", href: "/signals/activity", key: "heart.navActivity" },
];

/** Title of a body-signals page with the section's four pages as tabs, so the owner always knows where they are. */
export async function SignalsHeader({ current, title, intro }: { current: SignalsPage; title: string; intro: string }) {
  const { t } = await getI18n();
  return (
    <header className="space-y-4">
      <div>
        <h1 className="text-4xl font-semibold">{title}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{intro}</p>
      </div>
      <nav aria-label={t("heart.navLabel")} className="-mx-1 overflow-x-auto px-1 pb-1">
        <ul className="inline-flex rounded-2xl bg-muted p-[3px] text-sm">
          {PAGES.map(({ page, href, key }) => (
            <li key={page}>
              <Link href={href} aria-current={page === current ? "page" : undefined}
                className={cn("flex h-8 items-center whitespace-nowrap rounded-xl px-3.5 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
                  page === current ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>
                {t(key)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
