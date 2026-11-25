import { errorMessage } from "@/lib/api-error";

import { parseLocale } from "@/lib/i18n/config";
import { translate, type Key } from "@/lib/i18n/translate";

// These helpers run in the browser, where the page's <html lang> is the language the visitor chose.
const say = (key: Key) => translate(parseLocale(document.documentElement.lang), key);

/** Calls the proxied API and returns the JSON body (undefined for 204); throws an Error whose message is fit to show. */
export async function sendJson<T = void>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(say("common.apiUnreachable"));
  }
  if (!res.ok) throw new Error(await errorMessage(res, say("common.requestFailed")));
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try { res = await fetch(`/api/${path}`, { cache: "no-store" }); } catch { throw new Error(say("common.apiUnreachable")); }
  if (!res.ok) throw new Error(await errorMessage(res, say("common.requestFailed")));
  return res.json() as Promise<T>;
}

/** Uploads one file as multipart `file` to the proxied API; throws an Error whose message is fit to show. */
export async function postFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try { res = await fetch(`/api/${path}`, { method: "POST", body: form }); } catch { throw new Error(say("common.apiUnreachable")); }
  if (!res.ok) throw new Error(await errorMessage(res, say("common.requestFailed")));
  return res.json() as Promise<T>;
}

/** Posts a multipart form to the proxied API; throws an Error whose message is fit to show. */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  let res: Response;
  try { res = await fetch(`/api/${path}`, { method: "POST", body: form }); } catch { throw new Error(say("common.apiUnreachable")); }
  if (!res.ok) throw new Error(await errorMessage(res, say("common.requestFailed")));
  return res.json() as Promise<T>;
}

/** Posts a multipart form to an NDJSON streaming endpoint: calls onDelta with each piece of text and returns the final `done` payload. */
export async function postStream<T>(path: string, form: FormData, onDelta: (text: string) => void): Promise<T> {
  let res: Response;
  try { res = await fetch(`/api/${path}`, { method: "POST", body: form }); } catch { throw new Error(say("common.apiUnreachable")); }
  if (!res.ok || !res.body) throw new Error(await errorMessage(res, say("common.requestFailed")));
  const reader = res.body.getReader(), decoder = new TextDecoder();
  let buffer = "", done: T | undefined;
  const handle = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as { delta?: string; done?: T; error?: string };
    if (event.error) throw new Error(event.error);
    if (event.delta) onDelta(event.delta);
    if (event.done) done = event.done;
  };
  for (;;) {
    const { value, done: end } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    lines.forEach(handle);
    if (end) break;
  }
  handle(buffer);
  if (done === undefined) throw new Error(say("common.requestFailed"));
  return done;
}
