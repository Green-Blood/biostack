import type { Key } from "@/lib/i18n/translate";

export const THEME_COOKIE = "biostack_theme";

export type ThemeId = "auto" | "paper" | "clinic" | "sage" | "night" | "midnight" | "graphite";

type Theme = { id: Exclude<ThemeId, "auto">; dark: boolean; label: Key; swatch: [background: string, accent: string, ink: string] };

// Swatch colours are fixed previews of each theme, so the picker looks the same whichever theme is active.
export const THEMES: readonly Theme[] = [
  { id: "paper", dark: false, label: "nav.themePaper", swatch: ["#f4f6f5", "#0e6e7e", "#14232b"] },
  { id: "clinic", dark: false, label: "nav.themeClinic", swatch: ["#f5f8fc", "#1d63d8", "#0c2036"] },
  { id: "sage", dark: false, label: "nav.themeSage", swatch: ["#f1f4ee", "#3b7a56", "#1d2a21"] },
  { id: "night", dark: true, label: "nav.themeNight", swatch: ["#0f1a1f", "#4fb3c4", "#e6eceb"] },
  { id: "midnight", dark: true, label: "nav.themeMidnight", swatch: ["#0b1020", "#8aa4ff", "#e8ecff"] },
  { id: "graphite", dark: true, label: "nav.themeGraphite", swatch: ["#141414", "#f0b44c", "#ececec"] },
];

export function parseTheme(value: string | undefined | null): ThemeId {
  return THEMES.some((t) => t.id === value) ? (value as ThemeId) : "auto";
}

export const isDark = (id: ThemeId): boolean => THEMES.find((t) => t.id === id)?.dark ?? false;
