"use client";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { Check } from "lucide-react";
import { setTheme } from "@/app/actions/set-theme";
import { useI18n } from "@/lib/i18n/client";
import { THEMES, type ThemeId } from "@/lib/theme";

type Option = { id: ThemeId; label: string; bg: string; accent: string };

/** A round preview of a theme: its page colour with its accent dot in the middle. */
function Swatch({ bg, accent }: { bg: string; accent: string }) {
  return (
    <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-full border border-black/10" style={{ background: bg }}>
      <span className="size-2 rounded-full" style={{ background: accent }} />
    </span>
  );
}

export function ThemePicker({ current, variant = "dots" }: { current: ThemeId; variant?: "dots" | "rows" }) {
  const router = useRouter();
  const { t } = useI18n();
  const [pending, startTransition] = useTransition();

  function choose(id: ThemeId) {
    if (id === current) return;
    startTransition(async () => {
      await setTheme(id);
      router.refresh();
    });
  }

  // Automatic previews the colours in use right now, so it always matches what you see.
  const options: Option[] = [
    { id: "auto", label: t("nav.themeSystem"), bg: "var(--background)", accent: "var(--primary)" },
    ...THEMES.map((theme) => ({ id: theme.id, label: t(theme.label), bg: theme.swatch[0], accent: theme.swatch[1] })),
  ];

  if (variant === "rows") {
    return (
      <div role="radiogroup" aria-label={t("nav.theme")} className="grid grid-cols-2 gap-2">
        {options.map((o) => {
          const active = current === o.id;
          return (
            <button key={o.id} type="button" role="radio" aria-checked={active} disabled={pending} onClick={() => choose(o.id)}
              className={`flex items-center gap-2 rounded-2xl border px-2.5 py-2.5 text-sm transition-colors ${active ? "border-primary bg-primary/10 font-medium" : "border-border/70 text-muted-foreground hover:bg-accent hover:text-accent-foreground"}`}>
              <Swatch bg={o.bg} accent={o.accent} />
              <span className="min-w-0 flex-1 truncate text-left">{o.label}</span>
              {active && <Check className="size-4 shrink-0 text-primary" aria-hidden />}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div role="radiogroup" aria-label={t("nav.theme")} className="grid grid-cols-7 gap-1">
        {options.map((o) => {
          const active = current === o.id;
          return (
            <button key={o.id} type="button" role="radio" aria-checked={active} aria-label={o.label} title={o.label} disabled={pending}
              onClick={() => choose(o.id)}
              className={`grid place-items-center rounded-full p-0.5 transition-shadow ${active ? "ring-2 ring-primary" : "hover:ring-2 hover:ring-border"}`}>
              <Swatch bg={o.bg} accent={o.accent} />
            </button>
          );
        })}
      </div>
      <p className="truncate text-xs text-muted-foreground">{options.find((o) => o.id === current)?.label}</p>
    </div>
  );
}
