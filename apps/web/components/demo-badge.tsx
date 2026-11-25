"use client";
import { Badge } from "@/components/ui/badge";
import { useI18n } from "@/lib/i18n/client";

/** Marks a value that comes from the made-up demo data, so it can never be mistaken for a real result. */
export function DemoBadge() {
  const { t } = useI18n();
  return <Badge variant="outline" className="border-data/60 text-data">{t("common.demoBadge")}</Badge>;
}
