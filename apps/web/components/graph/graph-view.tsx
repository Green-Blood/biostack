"use client";
import { useEffect, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/client";
import type { T } from "@/lib/i18n/translate";
import type { GraphData } from "@/lib/types";
import { EdgeDetails } from "./edge-details";
import { GraphCanvas } from "./graph-canvas";
import { GraphEmpty } from "./graph-empty";
import { GraphLegend } from "./graph-legend";
import { focusSet } from "./layout";

async function readJson<R>(res: Response, t: T): Promise<R> {
  if (!res.ok) throw new Error(t("graph.serverAnswered", { status: res.status }));
  return res.json() as Promise<R>;
}

export function GraphView({ initial }: { initial: GraphData | null }) {
  const { t } = useI18n();
  const [data, setData] = useState<GraphData | null>(initial);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(initial ? "" : t("graph.loadFailed"));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFocusedId(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function recompute() {
    setBusy(true); setError(""); setStatus(t("graph.recomputing"));
    try {
      await readJson(await fetch("/api/analytics/recompute", { method: "POST" }), t);
      setData(await readJson<GraphData>(await fetch("/api/analytics/graph"), t));
      setFocusedId(null);
      setStatus(t("graph.recomputed"));
    } catch (e) {
      setStatus("");
      setError(t("graph.recomputeFailed", { message: (e as Error).message }));
    } finally { setBusy(false); }
  }

  const focus = data && focusedId ? focusSet(data, focusedId) : null;
  const focusedLabel = data?.nodes.find((n) => n.id === focusedId)?.label;
  const focusNote = focus && focusedLabel
    ? t("graph.focusMode", { label: focusedLabel, detail: focus.showsEffects ? t("graph.showsEffects") : t("graph.showsCauses") })
    : "";
  const hasEdges = (data?.edges.length ?? 0) > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={recompute} disabled={busy}><RefreshCw className="size-4" aria-hidden /> {t("graph.recompute")}</Button>
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">{status || focusNote}</p>
      </div>
      {error && <p role="alert" className="rounded-xl border border-outrange/50 p-3 text-sm text-outrange">{error}</p>}
      {data && !hasEdges && <GraphEmpty notes={data.notes} biomarkerCount={data.nodes.length} />}
      {data && data.nodes.length > 0 && (
        <>
          <div className="h-[24rem] overflow-hidden surface sm:h-[34rem]">
            <ReactFlowProvider><GraphCanvas data={data} focusedId={focusedId} onFocus={setFocusedId} /></ReactFlowProvider>
          </div>
          {hasEdges && <EdgeDetails edges={data.edges.filter((e) => !focus || focus.edges.has(e.id))} focusedLabel={focus ? focusedLabel ?? null : null} />}
          <GraphLegend />
        </>
      )}
    </div>
  );
}
