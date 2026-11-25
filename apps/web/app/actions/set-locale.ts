"use server";
import { cookies } from "next/headers";
import { LOCALE_COOKIE, parseLocale } from "@/lib/i18n/config";

export async function setLocale(value: string): Promise<void> {
  (await cookies()).set(LOCALE_COOKIE, parseLocale(value), { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
}
