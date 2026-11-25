"use client";
import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import type { MarkerSummaryFull } from "@/lib/types";
import { AttentionStrip } from "./attention-strip";
import { MarkerCard } from "./marker-card";
import { MarkerTable } from "./marker-table";
import { PanelInsight } from "./panel-insight";
import { SYSTEM_LABEL, SYSTEM_ORDER, byAttention, normalizeText, positionOf } from "./status";

type View = "systems" | "table";

export function MarkersView({ markers }: { markers: MarkerSummaryFull[] }) {
  const { t, tp } = useI18n();
  const [view, setView] = useState<View>("systems");
  const [q, setQ] = useState("");
  const [onlyOut, setOnlyOut] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const searching = q.trim() !== "";
  const rows = useMemo(() => {
    const needle = normalizeText(q.trim());
    return markers.filter((m) => (!onlyOut || positionOf(m).out) && (!needle || normalizeText(m.display_name).includes(needle) || m.marker_key.includes(needle)));
  }, [markers, q, onlyOut]);
  const attention = useMemo(() => rows.filter((m) => positionOf(m).out).sort(byAttention), [rows]);
  const sections = useMemo(() => {
    const known = new Set<string>(SYSTEM_ORDER);
    return SYSTEM_ORDER.map((key) => ({
      key,
      items: rows.filter((m) => (known.has(m.system) ? m.system : "other") === key).sort(byAttention),
    })).filter((s) => s.items.length > 0);
  }, [rows]);

  const tab = (v: View, label: string) => (
    <button type="button" aria-pressed={view === v} onClick={() => setView(v)}
      className={`rounded-xl px-3 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring ${view === v ? "bg-card font-medium shadow-card" : "text-muted-foreground hover:text-foreground"}`}>
      {label}
    </button>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div role="group" aria-label={t("biomarkers.viewLabel")} className="inline-flex gap-1 rounded-2xl bg-muted p-1">
          {tab("systems", t("biomarkers.viewSystems"))}
          {tab("table", t("biomarkers.viewTable"))}
        </div>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("biomarkers.findPlaceholder")} aria-label={t("biomarkers.findLabel")} title={t("biomarkers.searchHint")} className="w-full bg-card sm:max-w-xs" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyOut} onChange={(e) => setOnlyOut(e.target.checked)} className="size-4 accent-[var(--data)]" />
          {t("biomarkers.onlyOut")}
        </label>
        <span className="text-sm text-muted-foreground tnum sm:ml-auto">{t("biomarkers.shownOf", { shown: rows.length, total: markers.length })}</span>
      </div>

      {view === "table" ? <MarkerTable rows={[...rows].sort((a, b) => a.display_name.localeCompare(b.display_name))} /> : (
        <>
          {!onlyOut && !searching && <AttentionStrip markers={attention} />}
          {rows.length === 0 && <p className="rounded-2xl border border-dashed p-8 text-center text-muted-foreground">{t("biomarkers.noMatch")}</p>}
          {sections.map(({ key, items }) => {
            const open = searching || !collapsed[key];
            const out = items.filter((m) => positionOf(m).out).length;
            const name = t(SYSTEM_LABEL[key]);
            return (
              <section key={key} aria-labelledby={`sys-${key}`}>
                <h2 id={`sys-${key}`} className="text-lg font-semibold">
                  <button type="button" aria-expanded={open} aria-label={t("biomarkers.sectionToggle", { name })} onClick={() => setCollapsed({ ...collapsed, [key]: open })}
                    className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-xl py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <ChevronDown aria-hidden className={`size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none ${open ? "" : "-rotate-90"}`} />
                    <span>{name}</span>
                    <span className="text-sm font-normal text-muted-foreground tnum">{tp("biomarkers.sectionMarkers", items.length)}</span>
                    {out > 0 && <span className="text-sm font-normal text-outrange tnum">{t("biomarkers.sectionOut", { n: out })}</span>}
                  </button>
                </h2>
                {open && key !== "other" && (
                  <PanelInsight system={key} names={Object.fromEntries(items.map((m) => [m.marker_key, m.display_name]))}
                    outKeys={items.filter((m) => positionOf(m).out).map((m) => m.marker_key)} />
                )}
                {open && <ul className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{items.map((m) => <MarkerCard key={m.marker_key} m={m} />)}</ul>}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}
