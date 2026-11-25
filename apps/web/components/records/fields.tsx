"use client";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { Diagnosis, DiagnosisIn, DiagnosisStatus, RecordTreatment, TreatmentIn } from "@/lib/types";
import { Chip, Field, inputClass } from "./kit";

export const DX_STATUSES: { value: DiagnosisStatus; label: Key }[] = [
  { value: "suspected", label: "records.dxSuspected" },
  { value: "confirmed", label: "records.dxConfirmed" },
  { value: "ruled_out", label: "records.dxRuledOut" },
];

export type DxDraft = { key: number; name: string; icd10: string; status: DiagnosisStatus | "" };
export const emptyDx = (key: number): DxDraft => ({ key, name: "", icd10: "", status: "" });
export const dxFrom = (d: Diagnosis): DxDraft => ({ key: d.id, name: d.name, icd10: d.icd10 ?? "", status: d.status ?? "" });
export const dxBody = (d: DxDraft): DiagnosisIn => ({ name: d.name.trim(), icd10: d.icd10.trim() || null, status: d.status || undefined });

export function DiagnosisFields({ value, onChange, autoFocus }: { value: DxDraft; onChange: (v: DxDraft) => void; autoFocus?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <Field label={t("records.dxName")}>{(id) => <Input id={id} className={inputClass} value={value.name} autoFocus={autoFocus} onChange={(e) => onChange({ ...value, name: e.target.value })} placeholder={t("records.dxNamePh")} />}</Field>
        <Field label={t("records.dxCode")}>{(id) => <Input id={id} className={inputClass} value={value.icd10} onChange={(e) => onChange({ ...value, icd10: e.target.value })} placeholder="J18.9" />}</Field>
      </div>
      <div role="group" aria-label={t("records.dxStatus")} className="flex flex-wrap gap-2">
        {DX_STATUSES.map((s) => <Chip key={s.value} on={value.status === s.value} onClick={() => onChange({ ...value, status: value.status === s.value ? "" : s.value })}>{t(s.label)}</Chip>)}
      </div>
    </div>
  );
}

export const ROUTES: Key[] = ["records.routeTablets", "records.routeDrip", "records.routeInjection"];

export type TxDraft = { key: number; name: string; dosage: string; route: string; routeOther: boolean; frequency: string; start: string; end: string };
export const emptyTx = (key: number): TxDraft => ({ key, name: "", dosage: "", route: "", routeOther: false, frequency: "", start: "", end: "" });
export function txFrom(x: RecordTreatment, presets: string[]): TxDraft {
  const route = x.route ?? "";
  return { key: x.id, name: x.name, dosage: x.dosage ?? "", route, routeOther: route !== "" && !presets.includes(route), frequency: x.frequency ?? "", start: x.start_date ?? "", end: x.end_date ?? "" };
}
export const txBody = (x: TxDraft): TreatmentIn => ({
  name: x.name.trim(), dosage: x.dosage.trim() || null, route: x.route.trim() || null, frequency: x.frequency.trim() || null,
  start_date: x.start || null, end_date: x.end || null,
});

export function TreatmentFields({ value, onChange, autoFocus }: { value: TxDraft; onChange: (v: TxDraft) => void; autoFocus?: boolean }) {
  const { t } = useI18n();
  const labels = ROUTES.map((k) => t(k));
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("records.txName")}>{(id) => <Input id={id} className={inputClass} value={value.name} autoFocus={autoFocus} onChange={(e) => onChange({ ...value, name: e.target.value })} />}</Field>
        <Field label={t("records.txDose")}>{(id) => <Input id={id} className={inputClass} value={value.dosage} onChange={(e) => onChange({ ...value, dosage: e.target.value })} placeholder={t("records.txDosePh")} />}</Field>
      </div>
      <div className="space-y-1.5">
        <p className="text-sm font-medium" id={`route-${value.key}`}>{t("records.txHow")}</p>
        <div role="group" aria-labelledby={`route-${value.key}`} className="flex flex-wrap gap-2">
          {labels.map((l) => <Chip key={l} on={!value.routeOther && value.route === l} onClick={() => onChange({ ...value, route: value.route === l && !value.routeOther ? "" : l, routeOther: false })}>{l}</Chip>)}
          <Chip on={value.routeOther} onClick={() => onChange({ ...value, routeOther: !value.routeOther, route: value.routeOther ? "" : labels.includes(value.route) ? "" : value.route })}>{t("records.routeOther")}</Chip>
        </div>
        {value.routeOther && <Input aria-label={t("records.txHow")} className={inputClass} value={value.route} onChange={(e) => onChange({ ...value, route: e.target.value })} />}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label={t("records.txFrequency")}>{(id) => <Input id={id} className={inputClass} value={value.frequency} onChange={(e) => onChange({ ...value, frequency: e.target.value })} placeholder={t("records.txFrequencyPh")} />}</Field>
        <Field label={t("records.txFrom")}>{(id) => <Input id={id} type="date" className={inputClass} value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />}</Field>
        <Field label={t("records.txTo")}>{(id) => <Input id={id} type="date" className={inputClass} value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />}</Field>
      </div>
    </div>
  );
}
