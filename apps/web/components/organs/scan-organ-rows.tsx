"use client";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { OrganCatalogEntry, ScanOrigin, ScanSide } from "@/lib/types";
import { inputClass } from "@/components/records/kit";
import { cellKey, MAX_TEXT, type Cell, type Draft, type Param } from "./scan-model";
import { shownUnit } from "./table-model";

const ORIGIN: Record<ScanOrigin, Key> = { rule: "organs.scanOriginRule", ai: "organs.scanOriginAi", manual: "organs.scanOriginManual" };

/** Origin and verified badges for one stored value; an unverified value is italic with "?" like on the organ page. */
function Badges({ cell }: { cell: Cell }) {
  const { t } = useI18n();
  return (
    <p className="flex flex-wrap items-center gap-1 text-[11px] leading-tight text-muted-foreground">
      <span className="rounded-full border px-1.5 py-0.5">{t(ORIGIN[cell.origin])}</span>
      <span className={`rounded-full px-1.5 py-0.5 ${cell.verified ? "bg-primary/10 text-foreground" : "bg-muted italic"}`}>
        {cell.verified ? t("organs.scanVerified") : t("organs.scanNotVerified")}
      </span>
    </p>
  );
}

function ValueBox({ organ, param, side, label, cell, error, onChange, disabled }: {
  organ: string; param: Param; side: ScanSide; label: string; cell: Cell | undefined; error: boolean;
  onChange: (key: string, text: string) => void; disabled: boolean;
}) {
  const { t, unit } = useI18n();
  const key = cellKey(organ, param.key, side);
  const u = param.kind === "numeric" ? unit(shownUnit(param.unit)) : "";
  const shaky = cell && cell.text.trim() && !cell.verified;
  return (
    <div className="min-w-0 space-y-1">
      <label htmlFor={`scan-${key}`} className={side ? "block text-xs text-muted-foreground" : "sr-only"}>{label}</label>
      <div className="relative">
        <Input id={`scan-${key}`} className={`${inputClass} ${u ? "pr-14" : ""} ${shaky ? "italic" : ""}`} value={cell?.text ?? ""} disabled={disabled}
          inputMode={param.kind === "numeric" ? "decimal" : "text"} maxLength={param.kind === "text" ? MAX_TEXT : 12}
          aria-invalid={error || undefined} aria-describedby={error ? `scan-${key}-err` : undefined}
          onChange={(e) => onChange(key, e.target.value)} />
        {u && <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">{u}</span>}
        {shaky && <span aria-hidden className="absolute -top-1 -right-1 rounded-full bg-card px-1 text-xs font-semibold text-muted-foreground">?</span>}
      </div>
      {u && <span className="sr-only">{u}</span>}
      {cell && cell.text.trim() && <Badges cell={cell} />}
      {error && <p id={`scan-${key}-err`} role="alert" className="text-xs text-outrange">{t("organs.scanBadNumber")}</p>}
    </div>
  );
}

/** The editable measurements of one tagged organ: a box per parameter, left and right boxes where the parameter has sides. */
export function OrganRows({ organ, draft, bad, onChange, onRemove, disabled }: {
  organ: OrganCatalogEntry; draft: Draft; bad: Set<string>; onChange: (key: string, text: string) => void; onRemove: () => void; disabled: boolean;
}) {
  const { t } = useI18n();
  return (
    <section aria-label={organ.name} className="min-w-0 space-y-3 rounded-2xl border bg-card/60 p-3">
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 break-words font-medium">{organ.name}</h3>
        <button type="button" onClick={onRemove} disabled={disabled} aria-label={t("organs.scanRemoveOrgan", { name: organ.name })}
          className="inline-flex size-11 items-center justify-center rounded-full text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"><X className="size-4" aria-hidden /></button>
      </div>
      <div className="space-y-3">
        {organ.params.map((p) => (
          <fieldset key={p.key} className="min-w-0 space-y-1.5">
            <legend className="text-sm font-medium">{p.name}</legend>
            <div className={p.sides ? "grid grid-cols-2 gap-3" : "max-w-xs"}>
              {(p.sides ? (["left", "right"] as const) : (["" ] as const)).map((side) => (
                <ValueBox key={side} organ={organ.key} param={p} side={side} disabled={disabled}
                  label={side === "left" ? t("organs.scanSideLeft") : side === "right" ? t("organs.scanSideRight") : p.name}
                  cell={draft[cellKey(organ.key, p.key, side)]} error={bad.has(cellKey(organ.key, p.key, side))} onChange={onChange} />
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </section>
  );
}
