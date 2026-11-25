import type { GraphData } from "@/lib/types";

export const NODE_WIDTH = 190;
export const NODE_HEIGHT = 64;
const GAP_X = 170;
const GAP_Y = 28;

/** Layer of each node = length of the longest chain of precursors (capped, so a cycle cannot loop forever). */
function layers(data: GraphData): Map<string, number> {
  const layer = new Map(data.nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < data.nodes.length; pass++) {
    let changed = false;
    for (const e of data.edges) {
      const next = (layer.get(e.source) ?? 0) + 1;
      if (next > (layer.get(e.target) ?? 0) && next < data.nodes.length) { layer.set(e.target, next); changed = true; }
    }
    if (!changed) break;
  }
  return layer;
}

/** Deterministic left-to-right layering: precursors on the left, effects on the right, labs in a last column. */
export function layout(data: GraphData): Map<string, { x: number; y: number }> {
  const layer = layers(data);
  const linked = new Set(data.edges.flatMap((e) => [e.source, e.target]));
  const loose = data.nodes.filter((n) => !linked.has(n.id));
  const columns = new Map<number, string[]>();
  for (const n of data.nodes.filter((n) => linked.has(n.id))) {
    const col = layer.get(n.id) ?? 0;
    columns.set(col, [...(columns.get(col) ?? []), n.id]);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const columnCount = columns.size ? Math.max(...columns.keys()) + 1 : 0;
  const row = new Map<string, number>();
  for (const col of [...columns.keys()].sort((x, y) => y - x)) {
    const average = (id: string) => {
      const rows = data.edges.filter((e) => e.source === id).map((e) => row.get(e.target)).filter((r): r is number => r !== undefined);
      return rows.length ? rows.reduce((a, b) => a + b, 0) / rows.length : 0;
    };
    columns.get(col)!.sort((a, b) => average(a) - average(b) || a.localeCompare(b)).forEach((id, i) => {
      row.set(id, i);
      positions.set(id, { x: col * (NODE_WIDTH + GAP_X), y: i * (NODE_HEIGHT + GAP_Y) });
    });
  }
  loose.forEach((n, row) => positions.set(n.id, { x: columnCount * (NODE_WIDTH + GAP_X), y: row * (NODE_HEIGHT + GAP_Y) }));
  return positions;
}

/** Nodes and edges kept bright in Focus Mode: the node, its precursors, or its effects when it has no precursors. */
export function focusSet(data: GraphData, id: string): { nodes: Set<string>; edges: Set<string>; showsEffects: boolean } {
  const into = data.edges.filter((e) => e.target === id);
  const used = into.length ? into : data.edges.filter((e) => e.source === id);
  return {
    nodes: new Set([id, ...used.flatMap((e) => [e.source, e.target])]),
    edges: new Set(used.map((e) => e.id)),
    showsEffects: into.length === 0 && used.length > 0,
  };
}
