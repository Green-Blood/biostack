import { getI18n } from "@/lib/i18n/server";

export async function Recommendations({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  const { t } = await getI18n();
  return (
    <section aria-labelledby="rec-h" className="surface border-outrange/40 p-5">
      <h2 id="rec-h">{t("overview.recTitle")}</h2>
      <p className="mt-1 text-muted-foreground">{t("overview.recBody")}</p>
      <ul className="mt-3 list-disc space-y-1.5 pl-5">{items.map((r) => <li key={r}>{r}</li>)}</ul>
    </section>
  );
}
