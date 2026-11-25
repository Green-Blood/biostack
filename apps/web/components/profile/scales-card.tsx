"use client";
import { useRef, useState } from "react";
import { CheckCircle2, ChevronRight, FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import { postFile } from "@/lib/request";
import type { BodyKind, ScaleImportResult } from "@/lib/types";
import { cn } from "cn";
import { KINDS, metaOf } from "./body-kinds";

type State =
  | { step: "idle" }
  | { step: "reading"; file: string }
  | { step: "error"; message: string }
  | { step: "preview"; file: File; result: ScaleImportResult; failed?: string }
  | { step: "importing"; file: File; result: ScaleImportResult }
  | { step: "done"; result: ScaleImportResult };

const PREVIEW_ROWS = 10;
const skippedTotal = (r: ScaleImportResult) => r.skipped_total ?? r.skipped.length;
const URL = "profile/measurements/import";

function Fold({ title, children, open }: { title: string; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="group rounded-2xl border bg-card/60 px-4 py-2.5 text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-full font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none" />{title}
      </summary>
      <div className="mt-2 space-y-1.5 pl-6 text-muted-foreground">{children}</div>
    </details>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  const { formatNumber } = useI18n();
  return (
    <div className="min-w-0 rounded-2xl border bg-card/60 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-heading text-2xl font-semibold tnum">{formatNumber(value)}</p>
    </div>
  );
}

export function ScalesCard({ onImported }: { onImported: () => void }) {
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const [state, setState] = useState<State>({ step: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function pick(file: File | undefined) {
    if (!file) return;
    setState({ step: "reading", file: file.name });
    try { setState({ step: "preview", file, result: await postFile<ScaleImportResult>(`${URL}?dry_run=true`, file) }); }
    catch (err) { setState({ step: "error", message: (err as Error).message || t("profile.scalesReadFailed") }); }
  }

  async function confirm(file: File, preview: ScaleImportResult) {
    setState({ step: "importing", file, result: preview });
    try {
      const result = await postFile<ScaleImportResult>(`${URL}?dry_run=false`, file);
      setState({ step: "done", result });
      onImported();
    } catch (err) {
      setState({ step: "preview", file, result: preview, failed: (err as Error).message || t("profile.scalesImportFailed") });
    }
  }

  const reset = () => setState({ step: "idle" });
  const delimiter = (d: string) => ({ ",": t("profile.scalesDelComma"), ";": t("profile.scalesDelSemicolon"), "\t": t("profile.scalesDelTab"), "|": t("profile.scalesDelPipe") })[d] ?? d;

  return (
    <div className="space-y-4">
      <p className="max-w-prose text-sm text-muted-foreground">{t("profile.scalesIntro")}</p>

      <input ref={inputRef} type="file" accept=".csv,text/csv,text/plain" className="sr-only" tabIndex={-1} aria-label={t("profile.scalesDropAria")}
        onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }} />

      {state.step === "idle" || state.step === "error" ? (
        <div className="space-y-3">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); void pick(e.dataTransfer.files[0]); }}
            className={cn("empty-state flex flex-col items-center gap-3 px-5 py-8 text-center transition-colors duration-200 motion-reduce:transition-none", dragging && "border-primary bg-accent/60")}>
            <FileUp className="size-8 text-primary" aria-hidden />
            <p className="font-heading text-lg">{t("profile.scalesDropHeading")}</p>
            <p className="max-w-prose text-sm text-muted-foreground">{t("profile.scalesDropHint")}</p>
            <Button type="button" onClick={() => inputRef.current?.click()}>{t("profile.scalesChoose")}</Button>
          </div>
          {state.step === "error" && <p role="alert" className="text-sm text-outrange">{state.message}</p>}
        </div>
      ) : null}

      {state.step === "reading" && (
        <div role="status" className="space-y-2">
          <p className="text-sm text-muted-foreground">{t("profile.scalesReading")} <span className="tnum">{state.file}</span></p>
          <div className="skeleton h-16 rounded-2xl" aria-hidden />
        </div>
      )}

      {(state.step === "preview" || state.step === "importing") && (() => {
        const { result: r, file } = state;
        const busy = state.step === "importing";
        const shownKinds = KINDS.filter((m) => r.rows.some((row) => row.values[m.kind] != null));
        const rows = r.rows.slice(0, PREVIEW_ROWS);
        const n = r.total_rows; // distinct days that a real import would write
        return (
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold">{t("profile.scalesPreviewTitle", { file: file.name })}</h3>
              <p className="text-sm text-muted-foreground">{t("profile.scalesFormat", { delimiter: delimiter(r.delimiter), encoding: r.encoding })}</p>
            </div>

            <div className="min-w-0 space-y-2">
              <h4 className="eyebrow">{t("profile.scalesColumnsTitle")}</h4>
              {r.columns.length ? (
                <div className="overflow-x-auto rounded-2xl border">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/60 text-xs text-muted-foreground"><tr><th scope="col" className="px-3 py-2 font-medium">{t("profile.scalesColHeader")}</th><th scope="col" className="px-3 py-2 font-medium">{t("profile.scalesColReadAs")}</th></tr></thead>
                    <tbody className="divide-y">
                      {r.columns.map((c, i) => (
                        <tr key={`${c.header}${i}`}>
                          <td className="max-w-[12rem] break-words px-3 py-1.5">{c.header || "—"}</td>
                          <td className={cn("px-3 py-1.5", c.mapped_to ? "font-medium" : "text-muted-foreground")}>
                            {c.mapped_to === "date" ? t("profile.scalesColDate") : c.mapped_to ? t(metaOf(c.mapped_to as BodyKind).label) : t("profile.scalesColIgnored")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="text-sm text-outrange">{t("profile.scalesNoColumns")}</p>}
            </div>

            <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3">
              <Stat label={t("profile.scalesCountImport")} value={r.total_rows} />
              {r.would_replace_days != null && <Stat label={t("profile.scalesCountReplace")} value={r.would_replace_days} />}
              <Stat label={t("profile.scalesCountSkipped")} value={skippedTotal(r)} />
            </div>

            {r.warnings.length > 0 && (
              <div className="space-y-1 rounded-2xl border bg-card/60 px-4 py-2.5 text-sm">
                <p className="font-medium">{t("profile.scalesWarnings")}</p>
                <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">{r.warnings.map((w, i) => <li key={i} className="break-words">{w}</li>)}</ul>
              </div>
            )}
            {r.skipped.length > 0 && (
              <Fold title={`${t("profile.scalesSkippedList")} (${formatNumber(skippedTotal(r))})`}>
                <ul className="max-h-48 space-y-0.5 overflow-y-auto">{r.skipped.map((s, i) => <li key={i} className="break-words">{t("profile.scalesSkippedLine", { line: s.line, reason: s.reason })}</li>)}</ul>
              </Fold>
            )}

            {rows.length > 0 ? (
              <div className="min-w-0 space-y-2">
                <h4 className="eyebrow">{t("profile.scalesFirstRows")}</h4>
                <div className="overflow-x-auto rounded-2xl border">
                  <table className="w-full text-left text-sm tnum">
                    <thead className="bg-muted/60 text-xs text-muted-foreground">
                      <tr><th scope="col" className="px-3 py-2 font-medium">{t("profile.date")}</th>{shownKinds.map((m) => <th key={m.kind} scope="col" className="px-3 py-2 text-right font-medium">{t(m.label)}, {unit(m.unit)}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y">
                      {rows.map((row) => (
                        <tr key={row.date}>
                          <td className="whitespace-nowrap px-3 py-1.5">{formatDate(row.date)}</td>
                          {shownKinds.map((m) => <td key={m.kind} className="px-3 py-1.5 text-right">{row.values[m.kind] != null ? formatNumber(row.values[m.kind]!, { maximumFractionDigits: m.digits }) : "—"}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {r.total_rows > rows.length && <p className="text-xs text-muted-foreground">{t("profile.scalesFirstRowsOf", { shown: rows.length, total: r.total_rows })}</p>}
              </div>
            ) : null}

            {n === 0 && <p className="text-sm text-outrange">{t("profile.scalesNothingToImport")}</p>}
            {state.step === "preview" && state.failed && <p role="alert" className="text-sm text-outrange">{state.failed}</p>}
            <div className="flex flex-wrap items-center gap-3">
              {n > 0 && <Button type="button" size="lg" disabled={busy} onClick={() => void confirm(file, r)}>{busy ? t("profile.scalesImporting") : tp("profile.scalesImportBtn", n)}</Button>}
              <Button type="button" size="lg" variant="outline" disabled={busy} onClick={reset}>{t("profile.scalesCancel")}</Button>
            </div>
          </div>
        );
      })()}

      {state.step === "done" && (
        <div role="status" className="space-y-3">
          <p className="flex flex-wrap items-center gap-2 font-medium"><CheckCircle2 className="size-5 text-ok" aria-hidden />{t("profile.scalesDoneTitle")}. {t("profile.scalesDone", { imported: formatNumber(state.result.imported), replaced: formatNumber(state.result.replaced) })}{skippedTotal(state.result) > 0 && ` ${t("profile.scalesDoneSkipped", { n: formatNumber(skippedTotal(state.result)) })}`}{state.result.replaced_days != null && state.result.replaced_days > 0 && ` ${t("profile.scalesDoneDays", { n: formatNumber(state.result.replaced_days) })}`}</p>
          <Button type="button" variant="outline" onClick={reset}>{t("profile.scalesAnother")}</Button>
        </div>
      )}

      <Fold title={t("profile.scalesHelpTitle")}>
        <p>{t("profile.scalesHelp1")}</p>
        <p>{t("profile.scalesHelp2")}</p>
        <p>{t("profile.scalesHelp3")}</p>
      </Fold>
    </div>
  );
}
