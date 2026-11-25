"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, FileArchive, Ruler } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import { getJson, sendJson } from "@/lib/request";
import type { ImportJob, ImportStarted, Profile, SamsungImportSummary } from "@/lib/types";
import { localDay } from "./format";

const PATH = "imports/samsung-health";
const POLL_MS = 2000;

const STAGE: Record<string, Key> = {
  "": "signals.stageQueued", parse: "signals.stageParse", derive: "signals.stageDerive", sleep: "signals.stageSleep",
  workouts: "signals.stageWorkouts", daily: "signals.stageDaily", done: "signals.stageDone",
};
const COUNT: Record<string, Key> = {
  sleep: "signals.countSleep", stages: "signals.countStages", hrv: "signals.countHrv", skin: "signals.countSkin",
  resp: "signals.countResp", spo2: "signals.countSpo2", hr: "signals.countHr", steps: "signals.countSteps",
  stress: "signals.countStress", workouts: "signals.countWorkouts", body: "signals.countBody",
};

const active = (job: ImportJob | null) => job !== null && (job.status === "queued" || job.status === "running");

/** YYYY-MM-DD of a UTC timestamp in this computer's time zone. */
function Progress({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out motion-reduce:transition-none" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** POSTs the ZIP with XMLHttpRequest (fetch cannot report upload progress) through the same /api proxy. */
function uploadZip(file: File, onProgress: (fraction: number) => void, fallback: string, unreachable: string): Promise<ImportStarted> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/${PATH}`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.onerror = () => reject(new Error(unreachable));
    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText) as ImportStarted); } catch { reject(new Error(fallback)); }
        return;
      }
      reject(new Error(await errorMessage(new Response(xhr.responseText, { status: xhr.status }), fallback)));
    };
    xhr.send(form);
  });
}

function HeightOffer({ cm }: { cm: number }) {
  const { t, formatNumber } = useI18n();
  const [profileHeight, setProfileHeight] = useState<number | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getJson<Profile>("profile").then((p) => setProfileHeight(p.height_cm), () => setProfileHeight(undefined));
  }, []);
  const n = formatNumber(cm, { maximumFractionDigits: 1 });
  if (saved) return <p role="status" className="text-sm text-ok">{t("signals.heightSaved")}</p>;
  if (profileHeight !== null) return null; // unknown yet, or the profile already has a height: nothing to offer
  async function use() {
    setSaving(true); setError(null);
    try { await sendJson<Profile>("profile", "PUT", { height_cm: Math.round(cm * 10) / 10 }); setSaved(true); }
    catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-muted/50 p-3">
      <Ruler className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <p className="min-w-0 flex-1 basis-56 text-sm">{t("signals.heightOffer", { n })}</p>
      <Button type="button" variant="outline" onClick={use} disabled={saving}>{saving ? t("signals.heightSaving") : t("signals.useHeight", { n })}</Button>
      {error && <p role="alert" className="w-full text-sm text-outrange">{error}</p>}
    </div>
  );
}

function Summary({ job }: { job: ImportJob }) {
  const { t, tp, formatDate, formatNumber } = useI18n();
  const s = job.summary as Partial<SamsungImportSummary>;
  const w = s.workouts;
  const counts = Object.entries(s.counts ?? {});
  const skipped = Object.entries(s.skipped ?? {});
  const junk = Object.entries(s.junk ?? {}).filter(([, n]) => n > 0);
  const num = (n: number) => formatNumber(n, { maximumFractionDigits: 0 });
  return (
    <div className="space-y-4 rounded-2xl border bg-card/60 p-4">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-medium">
        <CheckCircle2 className="size-4 text-primary" aria-hidden />{t("signals.doneTitle")}
        {job.finished_at && <span className="text-sm font-normal text-muted-foreground tnum">{t("signals.doneAt", { date: formatDate(localDay(job.finished_at)) })}</span>}
      </p>
      <ul className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 tnum">
        <li>{tp("signals.sumNights", s.nights ?? 0, { n: num(s.nights ?? 0) })}</li>
        <li>{tp("signals.sumDays", s.days ?? 0, { n: num(s.days ?? 0) })}</li>
        {w && (
          <li>{tp("signals.sumWorkouts", w.added + w.updated + w.unchanged, { n: num(w.added + w.updated + w.unchanged) })}
            <span className="block text-xs text-muted-foreground">{t("signals.sumWorkoutsDetail", { added: num(w.added), updated: num(w.updated), unchanged: num(w.unchanged) })}</span></li>
        )}
        <li>{tp("signals.sumBody", s.body ?? 0, { n: num(s.body ?? 0) })}</li>
      </ul>
      {(s.dropped_workouts ?? 0) > 0 && <p className="text-sm text-muted-foreground tnum">{tp("signals.droppedWorkouts", s.dropped_workouts!, { n: num(s.dropped_workouts!) })}</p>}
      {s.latest_height_cm != null && <HeightOffer cm={s.latest_height_cm} />}
      <div className="space-y-1">
        {counts.length > 0 && (
          <details className="group text-sm">
            <summary className="cursor-pointer py-1 text-muted-foreground hover:text-foreground">{t("signals.readTitle")}</summary>
            <dl className="mt-1 grid max-w-md grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 pl-4 tnum">
              {counts.map(([k, n]) => (
                <div key={k} className="contents"><dt className="min-w-0 text-muted-foreground">{COUNT[k] ? t(COUNT[k]) : k}</dt><dd className="text-right">{num(n)}</dd></div>
              ))}
            </dl>
          </details>
        )}
        {skipped.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer py-1 text-muted-foreground hover:text-foreground">{tp("signals.skippedTitle", skipped.length)}</summary>
            <ul className="mt-1 space-y-0.5 pl-4">
              {skipped.map(([type, reason]) => (
                <li key={type} className="min-w-0 break-words"><code className="text-xs">{type}</code> <span className="text-muted-foreground">— {reason === "not imported" ? t("signals.reasonNotImported") : reason}</span></li>
              ))}
            </ul>
          </details>
        )}
        {junk.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer py-1 text-muted-foreground hover:text-foreground">{t("signals.junkTitle")}</summary>
            <ul className="mt-1 space-y-0.5 pl-4 tnum">
              {junk.map(([type, n]) => <li key={type} className="min-w-0 break-words">{t("signals.junkItem", { name: type, n: num(n) })}</li>)}
            </ul>
          </details>
        )}
      </div>
      <Link href="/signals" className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-4 hover:underline">
        {t("signals.openSignals")}<ArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  );
}

export function SamsungImportCard() {
  const { t, formatNumber } = useI18n();
  const [job, setJob] = useState<ImportJob | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumed, setResumed] = useState(false);
  const [retry, setRetry] = useState(0);
  const pick = useRef<HTMLInputElement>(null);

  // On load: show the latest import, and keep following it if it is still running (e.g. after a page reload).
  useEffect(() => {
    getJson<ImportJob | null>(`${PATH}/latest`).then((latest) => {
      setJob((current) => current ?? latest);
      if (active(latest)) setResumed(true);
    }, () => { /* the card still works without the history */ });
  }, []);

  // Poll a running job every 2 s until it is done or failed.
  useEffect(() => {
    if (!job || !active(job)) return;
    const timer = setTimeout(() => {
      getJson<ImportJob>(`${PATH}/${job.id}`).then(
        (next) => { setJob(next); setError(null); },
        (e: Error) => { setError(e.message); setRetry((n) => n + 1); },
      );
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [job, retry]);

  async function start(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) { setError(t("signals.notZip")); return; }
    setError(null); setResumed(false); setJob(null); setUpload(0);
    try {
      const { job_id } = await uploadZip(file, setUpload, t("common.requestFailed"), t("common.apiUnreachable"));
      setJob({ id: job_id, status: "queued", progress: 0, stage: "", summary: {}, error: null, started_at: null, finished_at: null });
    } catch (e) {
      setError((e as Error).message);
      // Another import may already be running (409): show and follow it.
      getJson<ImportJob | null>(`${PATH}/latest`).then((latest) => { if (active(latest)) { setJob(latest); setResumed(true); } }, () => {});
    } finally {
      setUpload(null);
    }
  }

  const busy = upload !== null || active(job);
  const pct = (f: number) => formatNumber(f, { style: "percent", maximumFractionDigits: 0 });
  return (
    <div className="space-y-4">
      <p className="max-w-prose text-sm text-muted-foreground">{t("signals.importText")}</p>
      <p className="max-w-prose text-xs text-muted-foreground">{t("signals.importPrivacy")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" size="lg" disabled={busy} onClick={() => pick.current?.click()}><FileArchive aria-hidden />{t("signals.chooseZip")}</Button>
        <input ref={pick} type="file" accept=".zip,application/zip" className="sr-only" tabIndex={-1} aria-hidden
          onChange={(e) => { void start(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {upload !== null && (
        <div className="max-w-xl space-y-1.5">
          <p role="status" className="text-sm tnum">{t("signals.uploading", { pct: pct(upload) })}</p>
          <Progress value={upload} label={t("signals.progressLabel")} />
        </div>
      )}
      {job && active(job) && (
        <div className="max-w-xl space-y-1.5">
          {resumed && <p className="text-xs text-muted-foreground">{t("signals.resumed")}</p>}
          <p role="status" className="flex justify-between gap-3 text-sm tnum">
            <span>{t(STAGE[job.stage] ?? "signals.stageQueued")}</span><span className="text-muted-foreground">{pct(job.progress)}</span>
          </p>
          <Progress value={job.progress} label={t("signals.progressLabel")} />
        </div>
      )}
      {job?.status === "done" && <Summary job={job} />}
      {job?.status === "failed" && (
        <div role="alert" className="max-w-xl space-y-1 rounded-2xl border border-outrange/40 p-4 text-sm">
          <p className="font-medium">{t("signals.failedTitle")}</p>
          {job.error && <p className="text-muted-foreground">{job.error}</p>}
        </div>
      )}
      {error && <p role="alert" className="max-w-prose text-sm text-outrange">{error}</p>}
    </div>
  );
}
