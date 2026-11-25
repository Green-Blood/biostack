import type { ReactNode } from "react";

/** One section heading style for the whole overview: serif title, quiet subtitle, optional action on the right. */
export function SectionHeader({ id, title, sub, action }: { id: string; title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
      <div>
        <h2 id={id}>{title}</h2>
        {sub && <p className="mt-0.5 text-sm text-muted-foreground">{sub}</p>}
      </div>
      {action}
    </div>
  );
}
