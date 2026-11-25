"use client";
import { useCallback, useEffect, useMemo } from "react";
import { Background, Controls, MarkerType, ReactFlow, useReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useI18n } from "@/lib/i18n/client";
import type { T } from "@/lib/i18n/translate";
import type { GraphData, GraphEdge } from "@/lib/types";
import { EFFECT_COLOR } from "./edge-details";
import { GraphNodeCard, type FlowNode } from "./graph-node";
import { focusSet, layout } from "./layout";

const NODE_TYPES = { bio: GraphNodeCard };
// A floor on the zoom keeps node text readable on a phone; the canvas can be panned.
const FIT = { padding: 0.15, minZoom: 0.5, duration: 0 };

const EFFECT_KEY = { worsens: "graph.effectWorsens", improves: "graph.effectImproves", unclear: "graph.effectUnclear" } as const;

export function edgeLabel(e: GraphEdge, t: T): string {
  return `${e.lagged ? `${e.lag_label} · ` : ""}${t(EFFECT_KEY[e.effect])}`;
}

function toEdge(e: GraphEdge, focus: ReturnType<typeof focusSet> | null, t: T): Edge {
  const dimmed = focus !== null && !focus.edges.has(e.id);
  const color = EFFECT_COLOR[e.effect];
  return {
    id: e.id, source: e.source, target: e.target, label: edgeLabel(e, t), type: "default",
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14, markerUnits: "userSpaceOnUse" },
    style: { stroke: color, strokeWidth: 1 + e.strength * 5, strokeDasharray: e.lagged ? "9 6" : undefined, opacity: dimmed ? 0.12 : 1 },
    labelStyle: { fill: "var(--foreground)", fontSize: 12, fontWeight: 500, opacity: dimmed ? 0.15 : 1 },
    labelBgStyle: { fill: "var(--card)", opacity: dimmed ? 0.15 : 0.95 },
    labelBgPadding: [6, 3], labelBgBorderRadius: 4,
    ariaLabel: t("graph.edgeAria", { phrase: e.phrase, days: e.n_days }),
  };
}

type Props = { data: GraphData; focusedId: string | null; onFocus: (id: string | null) => void };

export function GraphCanvas({ data, focusedId, onFocus }: Props) {
  const { fitView } = useReactFlow();
  const { t } = useI18n();
  const positions = useMemo(() => layout(data), [data]);
  const focus = useMemo(() => (focusedId ? focusSet(data, focusedId) : null), [data, focusedId]);
  const toggle = useCallback((id: string) => onFocus(id), [onFocus]);

  const nodes: FlowNode[] = useMemo(() => data.nodes.map((node) => ({
    id: node.id, type: "bio", position: positions.get(node.id) ?? { x: 0, y: 0 }, draggable: false, selectable: false, focusable: false, style: { pointerEvents: "all" },
    data: { node, dimmed: focus !== null && !focus.nodes.has(node.id), focused: node.id === focusedId, onFocus: toggle },
  })), [data, positions, focus, focusedId, toggle]);
  const edges = useMemo(() => data.edges.map((e) => toEdge(e, focus, t)), [data, focus, t]);

  useEffect(() => { void fitView(FIT); }, [data, fitView]);

  return (
    <ReactFlow
      nodes={nodes} edges={edges} nodeTypes={NODE_TYPES} fitView fitViewOptions={FIT} minZoom={0.3} maxZoom={1.5}
      nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} edgesFocusable={false}
      onPaneClick={() => onFocus(null)} proOptions={{ hideAttribution: true }}
      aria-label={t("graph.canvasAria")}
    >
      <Background gap={24} color="var(--border)" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
