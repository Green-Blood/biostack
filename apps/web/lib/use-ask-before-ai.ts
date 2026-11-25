import { useSyncExternalStore } from "react";

const KEY = "biostack.askBeforeAi";
const EVENT = "biostack:ask-before-ai";

const read = (): boolean => {
  try { return localStorage.getItem(KEY) !== "off"; } catch { return true; }
};

const subscribe = (notify: () => void) => {
  window.addEventListener(EVENT, notify);
  window.addEventListener("storage", notify);
  return () => { window.removeEventListener(EVENT, notify); window.removeEventListener("storage", notify); };
};

/** One-time "confirm before sending to AI" setting, on by default, kept in this browser only. */
export function useAskBeforeAi(): [boolean, (ask: boolean) => void] {
  const ask = useSyncExternalStore(subscribe, read, () => true);
  const set = (next: boolean) => {
    try { localStorage.setItem(KEY, next ? "on" : "off"); } catch { /* storage blocked: the default stays on */ }
    window.dispatchEvent(new Event(EVENT));
  };
  return [ask, set];
}
