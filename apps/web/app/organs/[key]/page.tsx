import Link from "next/link";
import { notFound } from "next/navigation";
import { Stethoscope } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { OrganDetail } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import { OrganView } from "@/components/organs/organ-view";

async function load(key: string): Promise<OrganDetail | null> {
  try { return await apiGet<OrganDetail>(`organs/${encodeURIComponent(key)}`); } catch { return null; }
}

export async function generateMetadata({ params }: { params: Promise<{ key: string }> }) {
  const { t } = await getI18n();
  const organ = await load(decodeURIComponent((await params).key));
  return { title: organ ? `${organ.name} · BioStack` : t("organs.pageTitle") };
}

export default async function OrganPage({ params }: { params: Promise<{ key: string }> }) {
  const { t, tp, formatDate } = await getI18n();
  const key = decodeURIComponent((await params).key);
  const organ = await load(key);
  if (!organ) notFound();
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const dated = organ.scans.filter((s) => s.date).map((s) => s.date!);
  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <Link href="/organs" className="text-sm text-muted-foreground underline-offset-4 hover:underline">{t("organs.back")}</Link>
          <h1 className="mt-1 break-words text-4xl font-semibold">{organ.name}</h1>
          {organ.scans.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground tnum">
              {tp("organs.scans", organ.scans.length)}
              {dated.length > 0 && ` · ${dated.length > 1 ? t("organs.scanSpan", { from: formatDate(dated[0]), to: formatDate(dated.at(-1)!) }) : formatDate(dated[0])}`}
            </p>
          )}
        </div>
        {organ.scans.length > 0 && (
          <Link href={`/organs/${encodeURIComponent(organ.key)}/doctor`}
            className="inline-flex h-9 items-center gap-2 rounded-xl border bg-card px-3.5 text-sm font-medium shadow-card outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">
            <Stethoscope aria-hidden className="size-4" />{t("organs.showToDoctor")}
          </Link>
        )}
      </header>
      <OrganView organ={organ} today={today} />
    </div>
  );
}
