import type { NextRequest } from "next/server";
import { apiUrl, authHeaders } from "@/lib/api";
import { hasValidApiKey, isPasswordEnabled, isValidSessionToken, SESSION_COOKIE } from "@/lib/access-auth";
import { isLocalRequest } from "@/lib/local-guard";
import { LOCALE_COOKIE, parseLocale } from "@/lib/i18n/config";

// Browser -> /api/* -> this proxy -> FastAPI with the bearer token added server-side.
async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  if (!isLocalRequest(req.headers)) return Response.json({ detail: "BioStack only answers on this machine" }, { status: 403 });
  const apiKey = req.headers.get("x-api-key"); // phone health sync (iOS Health Auto Export) authenticates with this header
  if (isPasswordEnabled()) {
    const sessionOk = isValidSessionToken(req.cookies.get(SESSION_COOKIE)?.value);
    const keyOk = hasValidApiKey(apiKey);
    if (!sessionOk && !keyOk) return Response.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const { path } = await ctx.params;
  const target = apiUrl(path.join("/")) + req.nextUrl.search;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const res = await fetch(target, {
    method: req.method,
    headers: { ...authHeaders, ...(apiKey ? { "X-API-Key": apiKey } : {}), "Content-Type": req.headers.get("content-type") ?? "application/json", "Accept-Language": parseLocale(req.cookies.get(LOCALE_COOKIE)?.value) },
    body: hasBody ? req.body : undefined, // streamed, so large scan archives never sit in memory
    duplex: "half",
    cache: "no-store",
  } as RequestInit & { duplex: "half" });
  return new Response(res.body, { status: res.status, headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" } });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
