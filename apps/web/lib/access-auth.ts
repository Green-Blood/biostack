import "server-only";
import { createHash, createHmac, timingSafeEqual } from "crypto";

export const SESSION_COOKIE = "biostack_session";

function accessPassword(): string {
  return process.env.BIOSTACK_ACCESS_PASSWORD ?? "";
}

function hmacKey(): string {
  return `${process.env.API_SECRET_KEY ?? "dev-secret-change-me"}:${accessPassword()}`;
}

function sha256(value: string): Buffer {
  return createHash("sha256").update(value).digest();
}

export function isPasswordEnabled(): boolean {
  return accessPassword().length > 0;
}

export function verifyPassword(input: string): boolean {
  const expected = accessPassword();
  if (!expected) return true;
  return timingSafeEqual(sha256(input), sha256(expected));
}

export function makeSessionToken(): string {
  const payload = "biostack-auth";
  const sig = createHmac("sha256", hmacKey()).update(payload).digest("hex");
  return `${payload}.${sig}`;
}

export function isValidSessionToken(token: string | undefined): boolean {
  if (!isPasswordEnabled()) return true;
  if (!token) return false;
  const expected = makeSessionToken();
  return timingSafeEqual(sha256(token), sha256(expected));
}

export function hasValidApiKey(headerValue: string | null): boolean {
  const expected = process.env.API_SECRET_KEY ?? "";
  if (!expected || !headerValue) return false;
  return timingSafeEqual(sha256(headerValue), sha256(expected));
}
