import type { ReactNode } from "react";

/** A card-styled tooltip anchored to a point in chart pixels; flips below the point near the top and stays inside the chart width. */
export function TooltipBox({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const half = 120;
  const left = Math.min(Math.max(x, half + 4), Math.max(half + 4, width - half - 4));
  const above = y > 150;
  return (
    <div role="status" className="pointer-events-none absolute z-10 w-60 rounded-2xl border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-card"
      style={{ left, top: y, transform: above ? "translate(-50%, calc(-100% - 12px))" : "translate(-50%, 14px)" }}>
      {children}
    </div>
  );
}
