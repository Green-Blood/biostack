"use client";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Activity, FlaskConical, Pill, TrendingDown, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";
import type { GraphNode, GraphNodeKind } from "@/lib/types";

export type GraphNodeData = { node: GraphNode; dimmed: boolean; focused: boolean; onFocus: (id: string) => void };
export type FlowNode = Node<GraphNodeData, "bio">;

export const KINDS: Record<GraphNodeKind, { label: Key; hint: Key; Icon: typeof Activity; shape: string }> = {
  symptom: { label: "graph.kindSymptom", hint: "graph.hintSymptom", Icon: TrendingDown, shape: "rounded-[2rem] border-2 border-outrange/70" },
  trigger: { label: "graph.kindTrigger", hint: "graph.hintTrigger", Icon: Zap, shape: "rounded-xl border-2 border-data/70" },
  biomarker: { label: "graph.kindBiomarker", hint: "graph.hintBiomarker", Icon: FlaskConical, shape: "rounded-xl border-2 border-dashed border-foreground/50" },
  protector: { label: "graph.kindProtector", hint: "graph.hintProtector", Icon: Pill, shape: "rounded-xl border-2 border-inrange" },
};

export function GraphNodeCard({ data }: NodeProps<FlowNode>) {
  const { node, dimmed, focused, onFocus } = data;
  const { t } = useI18n();
  const { label: labelKey, Icon, shape } = KINDS[node.kind];
  const label = t(labelKey);
  const state = focused ? t("graph.stateFocused") : t("graph.stateShow");
  return (
    <div className={`transition-opacity motion-reduce:transition-none ${dimmed ? "opacity-25" : ""}`}>
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground" isConnectable={false} />
      <button
        type="button"
        onClick={() => onFocus(node.id)}
        aria-pressed={focused}
        aria-label={node.detail ? t("graph.nodeAriaDetail", { kind: label, label: node.label, detail: node.detail, state }) : t("graph.nodeAria", { kind: label, label: node.label, state })}
        className={`nodrag nopan flex h-16 w-[190px] cursor-pointer flex-col justify-center gap-0.5 bg-card px-3 text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring ${shape} ${focused ? "ring-2 ring-ring ring-offset-2 ring-offset-background" : ""}`}
      >
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="size-3.5 shrink-0" aria-hidden /> {label}</span>
        <span className="line-clamp-2 text-sm font-medium leading-tight">{node.label}</span>
        {node.detail && <span className="tnum truncate text-xs text-muted-foreground">{node.detail}</span>}
      </button>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" isConnectable={false} />
    </div>
  );
}
