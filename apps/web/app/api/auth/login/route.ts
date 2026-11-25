import type { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { isLocalRequest } from "@/lib/local-guard";
import { isPasswordEnabled, makeSessionToken, SESSION_COOKIE, verifyPassword } from "@/lib/access-auth";

export async function POST(req: NextRequest) {
  if (!isLocalRequest(req.headers)) {
    return Response.json({ detail: "BioStack only answers on this machine" }, { status: 403 });
  }
  if (!isPasswordEnabled()) {
    return Response.json({ ok: true });
  }
  const body = (await req.json().catch(() => ({}))) as { password?: unknown };
  const password = typeof body.password === "string" ? body.password : "";
  if (!verifyPassword(password)) {
    return Response.json({ detail: "Invalid password" }, { status: 401 });
  }
  (await cookies()).set(SESSION_COOKIE, makeSessionToken(), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return Response.json({ ok: true });
}
