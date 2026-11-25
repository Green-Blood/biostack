import type { Metadata } from "next";
import { Onest, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";
import { AccessGate } from "@/components/access-gate";
import { CommandPalette } from "@/components/search/command-palette";
import { DemoBanner } from "@/components/demo-banner";
import { I18nProvider } from "@/lib/i18n/client";
import { getI18n } from "@/lib/i18n/server";
import { cookies } from "next/headers";
import { isDark, parseTheme, THEME_COOKIE } from "@/lib/theme";
import { isPasswordEnabled, isValidSessionToken, SESSION_COOKIE } from "@/lib/access-auth";

// Both families cover Cyrillic, so Russian text is set in the intended faces rather than a fallback.
const sans = Onest({ variable: "--font-sans-face", subsets: ["latin", "cyrillic"] });
const serif = Source_Serif_4({ variable: "--font-serif-face", subsets: ["latin", "cyrillic"] });

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getI18n();
  return { title: "BioStack", description: t("common.appDescription") };
}

// "Automatic" resolves to Paper or Night from the system setting before first paint (no flash).
const themeScript = `try{var h=document.documentElement;if(h.dataset.theme==='auto'){var d=matchMedia('(prefers-color-scheme: dark)').matches;h.dataset.theme=d?'night':'paper';if(d)h.classList.add('dark')}}catch(e){}`;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const { locale } = await getI18n();
  const jar = await cookies();
  const theme = parseTheme(jar.get(THEME_COOKIE)?.value);
  const passwordEnabled = isPasswordEnabled();
  const unlocked = isValidSessionToken(jar.get(SESSION_COOKIE)?.value);
  return (
    <html lang={locale} data-theme={theme} className={`${sans.variable} ${serif.variable} h-full antialiased${isDark(theme) ? " dark" : ""}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full font-sans md:flex">
        <I18nProvider locale={locale}>
          {passwordEnabled && !unlocked ? (
            <div className="min-w-0 flex-1">
              <AccessGate />
            </div>
          ) : (
            <>
              <Sidebar theme={theme} passwordEnabled={passwordEnabled} />
              <CommandPalette />
              <div className="min-w-0 flex-1">
                <DemoBanner />
                <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-10 md:py-12">{children}</main>
              </div>
            </>
          )}
        </I18nProvider>
      </body>
    </html>
  );
}
