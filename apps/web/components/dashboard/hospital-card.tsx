import Link from "next/link";
import { ArrowRight, Bed, MessageCircleQuestion, NotebookPen } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";
import type { RecordDetail, RecordItem } from "@/lib/types";
import { isOngoing } from "@/components/records/meta";

/** Shown above everything else while a hospital stay is open; renders nothing when none is. */
export async function HospitalCard({ records }: { records: RecordItem[] }) {
  const { t, tp, formatDate } = await getI18n();
  const stays = records.filter((r) => r.record_type === "hospital_stay" && isOngoing(r));
  if (stays.length === 0) return null;
  const details = await Promise.all(stays.map((s) => apiGet<RecordDetail>(`records/${s.id}`).catch(() => null)));
  return (
    <div className="space-y-4">
      {stays.map((s, i) => {
        const d = details[i];
        const day = d?.stay_days ?? s.stay_days ?? null;
        const where = [d?.clinic ?? s.clinic, d?.department].filter(Boolean).join(" · ");
        const open = d ? d.notes.filter((n) => n.kind === "question" && !n.done).length : null;
        const latest = d ? [...d.notes].filter((n) => n.kind === "note").sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "") || b.id - a.id)[0] : undefined;
        return (
          <section key={s.id} aria-label={t("records.hospitalCardLabel")} className="surface space-y-4 border-primary/40 p-5">
            <div className="flex items-start gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground"><Bed className="size-5" aria-hidden /></span>
              <div className="min-w-0">
                <h2 className="text-xl font-semibold">{day != null ? t("records.hospitalDay", { n: day }) : t("records.hospitalNow")}</h2>
                <p className="break-words font-medium">{s.title}</p>
                {where && <p className="break-words text-sm text-muted-foreground">{where}</p>}
              </div>
            </div>
            {(open != null && open > 0) && (
              <p className="flex items-center gap-2 text-sm"><MessageCircleQuestion className="size-4 shrink-0 text-muted-foreground" aria-hidden />{tp("records.openQuestions", open)}</p>
            )}
            {latest && (
              <p className="min-w-0 rounded-2xl bg-muted/60 px-3.5 py-2.5 text-sm">
                <span className="tnum mr-2 font-medium text-muted-foreground">{latest.date ? formatDate(latest.date, { day: "numeric", month: "short" }) : ""}</span>
                <span className="line-clamp-2 break-words">{latest.text}</span>
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Link href={`/records/${s.id}?focus=note`} className={buttonVariants({ size: "lg" })}><NotebookPen aria-hidden />{t("records.addNoteCta")}</Link>
              <Link href={`/records/${s.id}`} className={buttonVariants({ size: "lg", variant: "outline" })}>{t("records.openRecord")}<ArrowRight aria-hidden /></Link>
            </div>
          </section>
        );
      })}
    </div>
  );
}
