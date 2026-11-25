import type { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { isLocalRequest } from "@/lib/local-guard";
import { SESSION_COOKIE } from "@/lib/access-auth";

export async function POST(req: NextRequest) {
  if (!isLocalRequest(req.headers)) {
    return Response.json({ detail: "BioStack only answers on this machine" }, { status: 403 });
  }
  (await cookies()).delete(SESSION_COOKIE);
  return Response.json({ ok: true });
}
