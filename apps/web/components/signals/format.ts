import type { ClientI18n } from "@/lib/i18n/client-core";
import type { SignalFreshness, SignalTileKey } from "@/lib/types";

/** Where the Samsung Health import lives (Settings). */
export const IMPORT_HREF = "/settings#samsung";

/** The day "recent" windows end on: the data's last day when it is stale, else the API's today. */
export const anchorOf = (f: SignalFreshness): string => (f.stale && f.as_of ? f.as_of : f.today);

/** The local calendar day (YYYY-MM-DD) of a UTC timestamp such as an import's finished_at. */
export function localDay(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Minutes as "7:05" plus the spoken form "7 h 5 min" for screen readers. */
export function duration(i18n: ClientI18n, minutes: number): { short: string; long: string } {
  const total = Math.max(0, Math.round(minutes));
  const h = Math.floor(total / 60), m = total % 60;
  return { short: i18n.t("signals.durationShort", { h, mm: String(m).padStart(2, "0") }), long: h ? i18n.t("signals.durationLong", { h, m }) : i18n.t("signals.minutes", { m }) };
}

/** A tile value as text, with the unit to show beside it (sleep is shown as h:mm, so its unit becomes hours). */
export function tileValue(i18n: ClientI18n, key: SignalTileKey, value: number, unit: string): { text: string; unit: string; spoken: string } {
  const n = (o: Intl.NumberFormatOptions) => i18n.formatNumber(value, o);
  switch (key) {
    case "sleep_total_min": {
      const d = duration(i18n, value);
      return { text: d.short, unit: i18n.t("signals.hoursUnit"), spoken: d.long };
    }
    case "skin_temp_delta": {
      const text = n({ maximumFractionDigits: 1, minimumFractionDigits: 1, signDisplay: "exceptZero" });
      return { text, unit, spoken: `${text} ${unit}` };
    }
    case "steps": {
      const text = n({ maximumFractionDigits: 0 });
      return { text, unit, spoken: `${text} ${unit}` };
    }
    case "resting_hr":
    case "hrv_sdnn": {
      const text = n({ maximumFractionDigits: 0 });
      return { text, unit, spoken: `${text} ${unit}` };
    }
    default: {
      const text = n({ maximumFractionDigits: 1 });
      return { text, unit, spoken: `${text} ${unit}` };
    }
  }
}

/** Where each tile leads. */
export const TILE_HREF: Record<SignalTileKey, string> = {
  sleep_total_min: "/signals/sleep",
  resting_hr: "/signals/heart",
  hrv_sdnn: "/signals/heart",
  skin_temp_delta: "/signals/heart",
  spo2_avg: "/signals/heart",
  steps: "/signals/activity",
  weight: "/profile",
};

/** What a tile says when it has no value: never "no data yet" or "the last 7 days" when the data is simply old.
 *  `hasSpark`: the tile has points in its 30-day spark. */
export function tileEmptyText(i18n: ClientI18n, hasSpark: boolean, f: SignalFreshness): string {
  if (f.stale && f.as_of) {
    const date = i18n.formatDate(f.as_of, { day: "numeric", month: "short", year: "numeric" });
    return i18n.t(hasSpark ? "signals.noRecentTo" : "signals.noneTo", { date });
  }
  return i18n.t(hasSpark ? "signals.noRecent" : "signals.noData");
}
