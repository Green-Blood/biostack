"use client";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";

/** A delete that asks once, in place, before doing anything. */
export function ConfirmDelete({ label, question, onConfirm, disabled, iconOnly = true }: { label: string; question: string; onConfirm: () => void; disabled?: boolean; iconOnly?: boolean }) {
  const { t } = useI18n();
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return iconOnly
      ? <Button type="button" variant="ghost" size="icon-lg" className="size-11" aria-label={label} disabled={disabled} onClick={() => setAsking(true)}><Trash2 aria-hidden /></Button>
      : <Button type="button" variant="ghost" size="lg" disabled={disabled} onClick={() => setAsking(true)}><Trash2 aria-hidden />{label}</Button>;
  }
  return (
    <span role="group" aria-label={question} className="flex flex-wrap items-center gap-2">
      <span className="text-sm">{question}</span>
      <Button type="button" variant="destructive" size="lg" disabled={disabled} autoFocus onClick={() => { setAsking(false); onConfirm(); }}>{t("records.yesDelete")}</Button>
      <Button type="button" variant="outline" size="lg" onClick={() => setAsking(false)}>{t("records.keep")}</Button>
    </span>
  );
}
