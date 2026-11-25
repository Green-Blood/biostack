import type { Risk } from "@/lib/types";
import { getI18n, type I18n } from "@/lib/i18n/server";

const THRESHOLD = 70;
const LEVELS = { low: "overview.levelLow", moderate: "overview.levelModerate", high: "overview.levelHigh" } as const;

function Gauge({ score, t }: { score: number; t: I18n["t"] }) {
  const alert = score > THRESHOLD;
  return (
    <div className="relative mt-3 h-8 w-full" role="img" aria-label={t("overview.gaugeLabel", { score, threshold: THRESHOLD })}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
      <div className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-sm bg-inrange" style={{ left: 0, width: `${THRESHOLD}%` }} />
      <div className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-sm bg-outrange/40" style={{ left: `${THRESHOLD}%`, right: 0 }} />
      <div className="absolute top-0 h-8 w-px bg-foreground" style={{ left: `${THRESHOLD}%` }} />
      <div className={`absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background ${alert ? "bg-outrange" : "bg-data"}`} style={{ left: `${score}%` }} />
    </div>
  );
}

export async function RiskMeter({ risk }: { risk: Risk }) {
  const { t, tp, formatNumber } = await getI18n();
  const { score } = risk;
  return (
    <section aria-labelledby="risk-h" className="surface p-5">
      <h2 id="risk-h">{t("overview.riskTitle")}</h2>
      {score === null ? (
        <div className="mt-3">
          <p className="font-medium">{t("overview.riskNoData")}</p>
          <p className="mt-1 max-w-prose text-muted-foreground">{risk.reason}</p>
        </div>
      ) : (
        <>
          <p className="mt-2 flex items-baseline gap-3">
            <span className={`tnum text-4xl font-semibold ${risk.alert ? "text-outrange" : ""}`}>{score}</span>
            <span className="text-muted-foreground">{risk.level ? t("overview.riskOutOfLevel", { level: t(LEVELS[risk.level]) }) : t("overview.riskOutOf")}</span>
          </p>
          <Gauge score={score} t={t} />
          <div className="relative h-4 text-xs text-muted-foreground" aria-hidden>
            <span className="absolute left-0">0</span>
            <span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${THRESHOLD}%` }}>{t("overview.gaugeAlert", { n: THRESHOLD })}</span>
            <span className="absolute right-0">100</span>
          </div>
          <h3 className="mt-5 text-lg">{t("overview.riskFactors")}</h3>
          <ul className="mt-2 divide-y">
            {risk.factors.map((f) => (
              <li key={f.key} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 py-2">
                <span className="font-medium">{f.label}{f.seen_in_days !== null && <span className="block text-xs font-normal text-muted-foreground">{tp("overview.seenInDays", f.seen_in_days)}</span>}</span>
                <span className="tnum text-right">{f.has_data ? t("overview.factorPoints", { points: formatNumber(f.points, { maximumFractionDigits: 0 }), weight: f.weight }) : t("overview.factorNoData")}</span>
                <span className="col-span-2 text-sm text-muted-foreground">{f.detail}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
