"use client";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { emptyRow, outOfRange, type EditableRow } from "@/lib/lab-rows";
import { RangeHint } from "@/components/profile/range-hint";
import { useI18n } from "@/lib/i18n/client";

const GRID = "grid grid-cols-2 gap-x-3 gap-y-2 md:grid-cols-[minmax(0,2.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_2rem] md:items-center";

function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <label className={`block text-xs text-muted-foreground md:text-sm ${className}`}>
      <span className="md:sr-only">{label}</span>
      {children}
    </label>
  );
}

function RangeNote({ row }: { row: EditableRow }) {
  const { t } = useI18n();
  const out = outOfRange(row);
  if (out === null) return <span className="text-xs text-muted-foreground">{row.text.trim() ? t("labs.textResult") : t("labs.noValueYet")}</span>;
  const noRange = row.refMin.trim() === "" && row.refMax.trim() === "";
  if (noRange) return <span className="flex flex-col gap-0.5 text-xs text-muted-foreground">{t("labs.noRange")}<RangeHint needs={row.needsProfile} /></span>;
  return out
    ? <span className="text-sm font-medium text-outrange">{t("labs.outOfRange")}</span>
    : <span className="text-sm text-muted-foreground">{t("labs.inRange")}</span>;
}

type Props = { rows: EditableRow[]; onChange: (rows: EditableRow[]) => void; markerListId: string };

export function ReviewTable({ rows, onChange, markerListId }: Props) {
  const { t } = useI18n();
  const update = (id: string, patch: Partial<EditableRow>) => onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const remove = (id: string) => onChange(rows.filter((r) => r.id !== id));
  return (
    <div className="space-y-3">
      <div className={`${GRID} hidden px-3 text-sm text-muted-foreground md:grid`} aria-hidden>
        <span>{t("labs.colMarker")}</span><span>{t("labs.colValue")}</span><span>{t("labs.colUnit")}</span><span>{t("labs.colRangeMin")}</span><span>{t("labs.colRangeMax")}</span><span>{t("labs.colStatus")}</span><span />
      </div>
      <ul className="space-y-3">
        {rows.map((r, i) => (
          <li key={r.id} className={`${GRID} rounded-2xl border bg-card p-3`}>
            <Field label={t("labs.colMarker")} className="col-span-2 md:col-span-1">
              <Input list={markerListId} value={r.name} onChange={(e) => update(r.id, { name: e.target.value })} aria-label={t("labs.markerNameRow", { n: i + 1 })} placeholder={t("labs.markerPlaceholder")} autoComplete="off" />
            </Field>
            <Field label={t("labs.colValue")}>
              <Input inputMode="decimal" value={r.value} onChange={(e) => update(r.id, { value: e.target.value })} aria-label={t("labs.valueRow", { n: i + 1 })} className="tnum" />
            </Field>
            <Field label={t("labs.colUnit")}>
              <Input value={r.unit} onChange={(e) => update(r.id, { unit: e.target.value })} aria-label={t("labs.unitRow", { n: i + 1 })} placeholder={t("labs.unitPlaceholder")} />
            </Field>
            <Field label={t("labs.colRangeMin")}>
              <Input inputMode="decimal" value={r.refMin} onChange={(e) => update(r.id, { refMin: e.target.value })} aria-label={t("labs.rangeMinRow", { n: i + 1 })} className="tnum" />
            </Field>
            <Field label={t("labs.colRangeMax")}>
              <Input inputMode="decimal" value={r.refMax} onChange={(e) => update(r.id, { refMax: e.target.value })} aria-label={t("labs.rangeMaxRow", { n: i + 1 })} className="tnum" />
            </Field>
            <div className="col-span-2 flex items-center justify-between gap-2 md:contents">
              <div aria-live="polite"><RangeNote row={r} /></div>
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => remove(r.id)} aria-label={r.name.trim() ? t("labs.removeRowNamed", { n: i + 1, name: r.name.trim() }) : t("labs.removeRow", { n: i + 1 })}>
                <X aria-hidden />
              </Button>
            </div>
            {r.text.trim() !== "" || outOfRange(r) === null ? (
              <Field label={t("labs.textResultLabel")} className="col-span-2 md:col-span-7">
                <Input value={r.text} onChange={(e) => update(r.id, { text: e.target.value })} aria-label={t("labs.textResultRow", { n: i + 1 })} placeholder={t("labs.textResultPlaceholder")} />
              </Field>
            ) : null}
          </li>
        ))}
      </ul>
      {rows.length === 0 && <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">{t("labs.noRows")}</p>}
      <Button type="button" variant="outline" onClick={() => onChange([...rows, emptyRow()])}><Plus aria-hidden /> {t("labs.addRow")}</Button>
    </div>
  );
}
