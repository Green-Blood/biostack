"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkline } from "@/components/biomarkers/sparkline";
import { Button } from "@/components/ui/button";
import { sendJson } from "@/lib/request";
import { useI18n } from "@/lib/i18n/client";
import { LOW_PCT, NOTICEABLE_PCT, TEST_SECONDS, TESTS_FOR_BASELINE } from "@/lib/tap-test";
import type { CnsTest } from "@/lib/types";


type Phase = "idle" | "ready" | "running" | "saving" | "done";

export function TapTest({ initial }: { initial: CnsTest[] }) {
  const { t, formatNumber } = useI18n();
  const [history, setHistory] = useState(initial);
  const [phase, setPhase] = useState<Phase>("idle");
  const [taps, setTaps] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(TEST_SECONDS);
  const [result, setResult] = useState<CnsTest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const count = useRef(0);
  const deadline = useRef(0);
  const pad = useRef<HTMLButtonElement>(null);

  const finish = useCallback(async () => {
    setPhase("saving");
    try {
      const saved = await sendJson<CnsTest>("cns/tests", "POST", { tap_count_10s: count.current });
      setResult(saved); setHistory((h) => [saved, ...h]); setPhase("done");
    } catch (e) {
      setError(t("journal.tapSaveError", { message: (e as Error).message, count: count.current })); setPhase("idle");
    }
  }, [t]);

  const tap = useCallback(() => {
    if (phase === "ready") { deadline.current = performance.now() + TEST_SECONDS * 1000; setPhase("running"); }
    if (phase === "ready" || phase === "running") { count.current += 1; setTaps(count.current); }
  }, [phase]);

  useEffect(() => {
    if (phase !== "ready" && phase !== "running") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      e.preventDefault(); tap();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, tap]);

  useEffect(() => {
    if (phase !== "running") return;
    const id = setInterval(() => {
      const left = Math.max(0, (deadline.current - performance.now()) / 1000);
      setSecondsLeft(left);
      if (left === 0) { clearInterval(id); void finish(); }
    }, 100);
    return () => clearInterval(id);
  }, [phase, finish]);

  function start() {
    count.current = 0; setTaps(0); setSecondsLeft(TEST_SECONDS); setResult(null); setError(null); setPhase("ready");
    requestAnimationFrame(() => pad.current?.focus());
  }

  /** One plain-language sentence for a finished test, judged against the 14-day average. */
  function describe(test: CnsTest): string {
    const { baseline_dev_pct: dev, baseline_mean: mean, baseline_samples: samples } = test;
    if (dev === null || mean === null) {
      const remaining = Math.max(0, TESTS_FOR_BASELINE - (samples + 1));
      return remaining > 0 ? t("journal.tapNeedBaseline", { needed: TESTS_FOR_BASELINE, remaining }) : t("journal.tapThree");
    }
    const params = { mean: formatNumber(Math.round(mean)), size: formatNumber(Math.abs(Math.round(dev))) };
    if (Math.abs(dev) < NOTICEABLE_PCT) return t("journal.tapInLine", params);
    if (dev > 0) return t("journal.tapAbove", params);
    return dev <= LOW_PCT ? t("journal.tapBelowLow", params) : t("journal.tapBelow", params);
  }

  const values = [...history].reverse().map((t) => t.tap_count_10s).slice(-14);
  const active = phase === "ready" || phase === "running";
  return (
    <section aria-labelledby="tap-title" className="space-y-5">
      <h2 id="tap-title" className="font-semibold">{t("journal.tapTitle")}</h2>
      <p className="max-w-prose text-sm text-muted-foreground">{t("journal.tapIntro", { seconds: TEST_SECONDS })}</p>
      {active || phase === "saving" ? (
        <button ref={pad} type="button" onPointerDown={tap} aria-label={t("journal.tapAria", { taps })}
          className="flex h-64 w-full touch-none select-none flex-col items-center justify-center gap-2 rounded-xl border-2 border-[var(--data)] bg-card outline-none focus-visible:ring-3 focus-visible:ring-ring/50 active:bg-accent md:h-80">
          <span className="font-heading tnum text-7xl font-semibold">{taps}</span>
          <span className="tnum text-muted-foreground">{phase === "ready" ? t("journal.tapBegin") : phase === "saving" ? t("journal.tapSaving") : t("journal.tapLeft", { n: Math.ceil(secondsLeft) })}</span>
        </button>
      ) : (
        <Button size="lg" onClick={start}>{result ? t("journal.tapStartAnother") : t("journal.tapStart")}</Button>
      )}
      <div aria-live="polite" className="space-y-1">
        {result && <p className="text-lg"><span className="tnum font-semibold">{t("journal.tapResult", { n: result.tap_count_10s })}</span> {describe(result)}</p>}
        {error && <p role="alert" className="text-sm text-outrange">{error}</p>}
      </div>
      {values.length >= 2 && (
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>{t("journal.tapLast", { n: values.length })}</span><Sparkline values={values} />
          <span className="tnum">{t("journal.tapLatest", { n: values.at(-1) ?? 0 })}</span>
        </div>
      )}
    </section>
  );
}
