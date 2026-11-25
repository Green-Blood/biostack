import "server-only";
import { cookies } from "next/headers";
import { LOCALE_COOKIE, parseLocale } from "@/lib/i18n/config";

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000";
const KEY = process.env.API_SECRET_KEY ?? "dev-secret-change-me";

export function apiUrl(path: string): string {
  return `${BASE}/api/v1/${path.replace(/^\//, "")}`;
}

export const authHeaders = { Authorization: `Bearer ${KEY}` } as const;

/** Server-component helper: GET JSON from the BioStack API with the server-held token. */
export async function apiGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const qs = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
  ).toString();
  const language = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  const res = await fetch(apiUrl(path) + (qs ? `?${qs}` : ""), { headers: { ...authHeaders, "Accept-Language": language }, cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} on ${path}`);
  return res.json() as Promise<T>;
}
