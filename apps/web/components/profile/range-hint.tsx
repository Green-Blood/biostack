"use client";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/client";
import type { NeedsProfile } from "@/lib/types";

const KEY = { sex: "profile.hintSex", age: "profile.hintAge", both: "profile.hintBoth" } as const;

/** Why a reference range is blank: the lab printed several and the profile lacks the field that picks one. */
export function RangeHint({ needs, className = "" }: { needs: NeedsProfile | null | undefined; className?: string }) {
  const { t } = useI18n();
  if (!needs) return null;
  return <Link href="/profile" className={`text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground ${className}`}>{t(KEY[needs])}</Link>;
}
