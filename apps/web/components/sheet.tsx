"use client";
import { useEffect, useRef, useState, type ReactNode, type PropsWithChildren } from "react";
import { X } from "lucide-react";

type Side = "right" | "left" | "bottom";

/**
 * Modal drawer built on <dialog> (native focus trap, Escape, backdrop), so no new dependency.
 * The panel is anchored to one edge; clicking the backdrop or the close button dismisses it.
 */
export function Sheet({
  trigger,
  children,
  footer,
  label,
  side = "right",
}: PropsWithChildren<{
  trigger: ReactNode;
  label: string;
  side?: Side;
  footer?: ReactNode;
}>) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);

  // <dialog> has no React onChange for backdrop clicks, and closing with Escape fires "close".
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const onClick = (e: MouseEvent) => { if (e.target === d) d.close(); };
    const onClose = () => setOpen(false);
    d.addEventListener("click", onClick);
    d.addEventListener("close", onClose);
    return () => { d.removeEventListener("click", onClick); d.removeEventListener("close", onClose); };
  }, []);

  function openSheet() { setOpen(true); ref.current?.showModal(); }
  function close() { setOpen(false); ref.current?.close(); }

  return (
    <>
      <button type="button" onClick={openSheet} aria-label={label}
        className="grid size-9 shrink-0 place-items-center rounded-full border border-border bg-card/70 text-foreground transition-colors hover:bg-card">
        {trigger}
      </button>
      <dialog
        ref={ref}
        aria-label={label}
        className={`m-0 h-dvh max-h-none w-full max-w-none border-0 bg-transparent p-0 outline-none open:flex ${
          side === "right" ? "justify-end" : side === "left" ? "justify-start" : "items-end"
        }`}
        style={{ marginLeft: 0, marginRight: 0, inset: 0, maxHeight: "100dvh" }}
        onClick={(e) => { if (e.target === ref.current) close(); }}
      >
        <div
          key={String(open)}
          className={`flex min-h-0 flex-1 flex-col border-border bg-sidebar shadow-2xl ${
            side === "right" ? "max-w-[22rem] border-l animate-sheet-right" : side === "left" ? "max-w-[22rem] border-r animate-sheet-left" : "h-auto max-h-[85dvh] animate-sheet-bottom border-t"
          }`}
        >
          <div className="flex items-center justify-between p-4 pb-0">
            <span className="sr-only">{label}</span>
            <button type="button" onClick={close} aria-label={label}
              className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground">
              <X className="size-5" aria-hidden />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-3 pb-6">
            {children}
          </div>
          {footer && (
            <div className="border-t border-border bg-sidebar p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
              {footer}
            </div>
          )}
        </div>
      </dialog>
    </>
  );
}
