"use client";
import Link from "next/link";
import { useI18n } from "@/lib/i18n/client";

export type TestIdea = { name: string; why: string };
export type Insight = { ai_enabled: boolean; tests_worth_it?: TestIdea[] };

export function TestLists({ worth, skip }: { worth?: TestIdea[]; skip?: TestIdea[] }) {
  const { t } = useI18n();
  const list = (title: string, items: TestIdea[] | undefined, tone: string) => items && items.length > 0 && (
    <div>
      <h4 className={`text-sm font-semibold ${tone}`}>{title}</h4>
      <ul className="mt-1 space-y-1 text-sm">
        {items.map((i) => <li key={i.name}><span className="font-medium">{i.name}</span> — <span className="text-muted-foreground">{i.why}</span></li>)}
      </ul>
    </div>
  );
  return <>{list(t("biomarkers.insightWorth"), worth, "text-ok")}{list(t("biomarkers.insightSkip"), skip, "text-muted-foreground")}</>;
}

export function AiOffNote() {
  const { t } = useI18n();
  return <p className="text-sm text-muted-foreground">{t("biomarkers.insightOff")} <Link href="/settings#ai" className="underline underline-offset-4">{t("biomarkers.insightSettings")}</Link>.</p>;
}
