"use client";
import { cn } from "cn";

/** A small radio switch in the same style as the period selector. */
export function Segmented<V extends string>({ value, onChange, options, label }: {
  value: V; onChange: (v: V) => void; options: { value: V; label: string }[]; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex shrink-0 rounded-2xl bg-muted p-[3px] text-sm">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cn("h-7 rounded-xl px-3 text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
            value === o.value ? "bg-card font-medium text-foreground shadow-card" : "hover:text-foreground")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
