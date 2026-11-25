"use client";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, BookOpen, FileText, HeartPulse, ListTree, Paperclip, Pill, ScanLine, Search, Stethoscope, X, type LucideIcon } from "lucide-react";
import { getJson } from "@/lib/request";
import { useI18n } from "@/lib/i18n/client";
import type { Key } from "@/lib/i18n/translate";

export const OPEN_SEARCH_EVENT = "biostack:open-search";

type Kind = "signals" | "organ" | "marker" | "record" | "file" | "medication" | "journal" | "imaging";
type Hit = {
  kind: Kind; id: number | string; title: string; subtitle: string; href: string; score: number;
  value?: number | null; unit?: string; date?: string; out_of_range?: boolean; is_demo?: boolean; snippet?: string;
};
type Group = { kind: Kind; total: number; hits: Hit[] };
type Response = { query: string; total: number; groups: Group[] };

const ICON: Record<Kind, LucideIcon> = { signals: HeartPulse, organ: Stethoscope, marker: Activity, record: ListTree, file: Paperclip, medication: Pill, journal: BookOpen, imaging: ScanLine };
const GROUP_LABEL: Record<Kind, Key> = {
  signals: "search.groupSignals", organ: "search.groupOrgan", marker: "search.groupMarker", record: "search.groupRecord", file: "search.groupFile",
  medication: "search.groupMedication", journal: "search.groupJournal", imaging: "search.groupImaging",
};
const RECENT_KEY = "biostack.recentSearches";
const MAX_RECENT = 5;

function readRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string").slice(0, MAX_RECENT) : [];
  } catch { return []; }
}
function writeRecent(list: string[]) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* storage unavailable: recents are optional */ }
}

export function CommandPalette() {
  const router = useRouter();
  const { t, tp, formatDate, formatNumber, unit } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [settled, setSettled] = useState<{ q: string; data: Response | null; failed: boolean } | null>(null);
  const [active, setActive] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);
  const [retry, setRetry] = useState(0);

  const show = useCallback(() => {
    setRecent(readRecent());
    setOpen(true);
    const d = dialogRef.current;
    if (d && !d.open) d.showModal();
  }, []);
  const hide = useCallback(() => {
    setOpen(false);
    const d = dialogRef.current;
    if (d?.open) d.close();
  }, []);

  // Cmd/Ctrl+K from anywhere, plus the sidebar button's custom event.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (dialogRef.current?.open) hide(); else show();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_SEARCH_EVENT, show);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener(OPEN_SEARCH_EVENT, show); };
  }, [show, hide]);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  // Debounced fetch; a late answer for an older query is ignored. State is only set from the async callback.
  const q = query.trim();
  useEffect(() => {
    if (!open || q.length < 2) return;
    let stale = false;
    const timer = setTimeout(async () => {
      try {
        const res = await getJson<Response>(`search?q=${encodeURIComponent(q)}`);
        if (!stale) { setSettled({ q, data: res, failed: false }); setActive(0); }
      } catch {
        if (!stale) setSettled({ q, data: null, failed: true });
      }
    }, 200);
    return () => { stale = true; clearTimeout(timer); };
  }, [q, open, retry]);

  const ready = q.length >= 2 && settled?.q === q;
  const loading = q.length >= 2 && !ready;
  const failed = ready && settled.failed;
  const data = q.length >= 2 ? settled?.data ?? null : null;

  const flat = useMemo(() => (data?.groups ?? []).flatMap((g) => g.hits), [data]);

  function go(hit: Hit) {
    if (q.length >= 2) writeRecent([q, ...readRecent().filter((r) => r !== q)].slice(0, MAX_RECENT));
    hide();
    router.push(hit.href);
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!flat.length) return;
      e.preventDefault();
      setActive((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + flat.length) % flat.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      // Only open a hit when the visible results belong to the text currently in the box, never to an earlier query.
      if (ready && !failed && flat[active]) go(flat[active]);
    }
  }

  useEffect(() => {
    document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active, listId, flat]);

  function subtitle(h: Hit) {
    if (h.kind === "marker") {
      const val = h.value == null ? "" : `${formatNumber(h.value)}${h.unit ? ` ${unit(h.unit)}` : ""}`;
      return [val || h.subtitle.split(" · ")[0], h.date ? formatDate(h.date, { day: "numeric", month: "short", year: "numeric" }) : ""].filter(Boolean).join(" · ");
    }
    return h.date ? h.subtitle.replace(h.date, formatDate(h.date, { day: "numeric", month: "short", year: "numeric" })) : h.subtitle;
  }

  const groups = data?.groups ?? [];
  const offsets = groups.map((_, i) => groups.slice(0, i).reduce((n, g) => n + g.hits.length, 0));
  return (
    <dialog ref={dialogRef} aria-label={t("search.dialogLabel")} onClose={() => setOpen(false)}
      onClick={(e) => { if (e.target === dialogRef.current) hide(); }}
      className="m-0 mx-auto mt-[8vh] max-h-[80vh] w-[calc(100%-2rem)] max-w-xl overflow-hidden rounded-[1.75rem] border border-border/60 bg-card p-0 text-card-foreground shadow-[0_24px_80px_rgb(0_0_0/0.28)] open:flex open:flex-col md:mt-[12vh]">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <input ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onInputKey}
          role="combobox" aria-expanded={flat.length > 0} aria-controls={listId} aria-autocomplete="list"
          aria-activedescendant={flat.length ? `${listId}-${active}` : undefined}
          aria-label={t("search.inputLabel")} placeholder={t("search.placeholder")} autoComplete="off" spellCheck={false}
          className="h-12 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground" />
        <button type="button" onClick={hide} aria-label={t("search.close")}
          className="grid size-8 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <X className="size-4" aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2" aria-busy={loading}>
        <p className="sr-only" role="status" aria-live="polite">
          {loading ? t("search.loading") : data && data.total > 0 ? tp("search.resultsCount", data.total) : ""}
        </p>

        {q.length < 2 && (
          <div className="space-y-4 p-3">
            {recent.length > 0 && (
              <section aria-label={t("search.recent")}>
                <div className="mb-1 flex items-center justify-between">
                  <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("search.recent")}</h2>
                  <button type="button" onClick={() => { writeRecent([]); setRecent([]); }}
                    className="rounded px-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{t("search.clearRecent")}</button>
                </div>
                <ul className="flex flex-wrap gap-1.5">
                  {recent.map((r) => (
                    <li key={r}>
                      <button type="button" onClick={() => { setQuery(r); inputRef.current?.focus(); }}
                        className="rounded-full border border-border px-3 py-1 text-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{r}</button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <div className="text-center">
              <p className="font-medium">{t("search.emptyTitle")}</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{q.length === 1 ? t("search.tooShort") : t("search.emptyHelp")}</p>
            </div>
          </div>
        )}

        {q.length >= 2 && loading && !data && <p className="p-6 text-center text-sm text-muted-foreground">{t("search.loading")}</p>}

        {q.length >= 2 && failed && (
          <div role="alert" className="space-y-2 p-6 text-center text-sm">
            <p>{t("search.error")}</p>
            <button type="button" onClick={() => { setSettled(null); setRetry((n) => n + 1); }}
              className="rounded-full border border-border px-4 py-1.5 hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{t("search.retry")}</button>
          </div>
        )}

        {q.length >= 2 && !failed && data && data.total === 0 && (
          <div className="p-6 text-center">
            <p className="font-medium">{t("search.nothingFound", { q })}</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{t("search.nothingFoundHelp")}</p>
          </div>
        )}

        {!failed && data && data.total > 0 && (
          <div id={listId} role="listbox" aria-label={t("search.dialogLabel")} className={loading ? "opacity-70 transition-opacity motion-reduce:transition-none" : ""}>
            {data.groups.map((g, gi) => {
              const Icon = ICON[g.kind] ?? FileText;
              return (
                <div key={g.kind} role="group" aria-label={t(GROUP_LABEL[g.kind])} className="mb-1">
                  <div className="flex items-baseline justify-between px-3 pt-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    <span>{t(GROUP_LABEL[g.kind])}</span>
                    {g.total > g.hits.length && <span className="font-normal normal-case tracking-normal">{t("search.more", { shown: g.hits.length, total: g.total })}</span>}
                  </div>
                  {g.hits.map((h, hi) => {
                    const i = offsets[gi] + hi;
                    const selected = i === active;
                    return (
                      <div key={`${h.kind}-${h.id}`} id={`${listId}-${i}`} role="option" aria-selected={selected}
                        onMouseMove={() => selected || setActive(i)} onClick={() => go(h)}
                        className={`flex cursor-pointer items-start gap-3 rounded-2xl px-3.5 py-2.5 transition-colors ${selected ? "bg-accent text-accent-foreground" : ""}`}>
                        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2">
                            <span className="truncate text-sm font-medium">{h.title}</span>
                            {h.out_of_range && <span className="text-xs font-medium text-outrange">{t("search.outOfRange")}</span>}
                            {h.is_demo && <span className="rounded border border-border px-1 text-[10px] uppercase text-muted-foreground">{t("search.demo")}</span>}
                          </div>
                          {subtitle(h) && <div className="truncate text-xs text-muted-foreground">{subtitle(h)}</div>}
                          {h.snippet && <div className="line-clamp-2 text-xs text-muted-foreground">{h.snippet}</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="hidden items-center gap-4 border-t border-border px-4 py-2 text-xs text-muted-foreground sm:flex">
        <span>{t("search.hintNavigate")}</span><span>{t("search.hintOpen")}</span><span>{t("search.hintClose")}</span>
      </div>
    </dialog>
  );
}
