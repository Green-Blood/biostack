"use client";
import { useId, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "cn";

/** A pill that toggles on/off (aria-pressed); 44px tall so it is easy to hit on a phone. */
export function Chip({ on, onClick, children, className, disabled }: { on: boolean; onClick: () => void; children: ReactNode; className?: string; disabled?: boolean }) {
  return (
    <button type="button" aria-pressed={on} disabled={disabled} onClick={onClick}
      className={cn("inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full border px-4 text-sm font-medium transition-[background-color,border-color,transform] duration-200 ease-[var(--ease-out)] outline-none focus-visible:ring-3 focus-visible:ring-ring/50 active:scale-[0.97] disabled:opacity-50 motion-reduce:transition-none",
        on ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card hover:bg-muted", className)}>
      {children}
    </button>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: (id: string) => ReactNode; className?: string }) {
  const id = useId();
  return (
    <div className={cn("min-w-0 space-y-1.5", className)}>
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      {children(id)}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export const ErrorLine = ({ message }: { message: string | null }) =>
  message ? <p role="alert" className="rounded-2xl border border-outrange/50 bg-card px-3.5 py-2.5 text-sm">{message}</p> : null;

/** A collapsible card; the heading button is the control, so it works by keyboard and screen reader. */
export function SectionCard({ title, count, defaultOpen = true, id, children, action }: { title: string; count?: number; defaultOpen?: boolean; id?: string; children: ReactNode; action?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  const body = useId();
  return (
    <section id={id} aria-label={title} className="surface min-w-0 scroll-mt-20">
      <div className="flex items-center gap-2 pr-3">
        <h2 className="min-w-0 flex-1 text-base font-semibold">
          <button type="button" aria-expanded={open} aria-controls={body} onClick={() => setOpen(!open)}
            className="flex min-h-12 w-full items-center gap-2 rounded-3xl px-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
            <span className="min-w-0 truncate">{title}</span>
            {count != null && count > 0 && <span className="tnum rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{count}</span>}
            <ChevronDown className={cn("ml-auto size-4 shrink-0 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none", open && "rotate-180")} aria-hidden />
          </button>
        </h2>
        {action}
      </div>
      <div id={body} hidden={!open} className="space-y-4 px-4 pb-4">{children}</div>
    </section>
  );
}

export const selectClass = "h-11 w-full min-w-0 rounded-xl border border-input bg-card/60 px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm";
export const inputClass = "h-11 md:h-10";

/** Runs one change against the API and then refreshes the page's record; keeps the busy flag and a localized error. */
export function useAction(reload: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true); setError(null);
    try { await fn(); await reload(); return true; }
    catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(false); }
  }
  return { busy, error, setError, run };
}
