/** Reads the FastAPI error body (string, {message}, or a list of validation errors) into one sentence. */
export async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail?.message === "string") return detail.message;
    if (Array.isArray(detail) && detail.length) return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join(" ");
  } catch { /* body was not JSON */ }
  return fallback;
}
