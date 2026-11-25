const LOCAL = ["localhost", "127.0.0.1", "[::1]", "::1"];

const hostnameOf = (value: string): string | null => {
  try { return new URL(value.includes("://") ? value : `http://${value}`).hostname.toLowerCase(); } catch { return null; }
};

const OWN_PAGES = new Set(["same-origin", "none"]);

/** Extra hostnames the owner trusts, e.g. this machine's Tailscale name: ALLOWED_HOSTS=box.tail1234.ts.net */
export function trustedHostnames(extra = process.env.ALLOWED_HOSTS ?? ""): Set<string> {
  const names = extra.split(",").map((name) => name.trim().toLowerCase()).filter(Boolean);
  return new Set([...LOCAL, ...names]);
}

/**
 * BioStack is private: refuse requests whose Host or Origin is not this machine or a hostname listed in ALLOWED_HOSTS
 * (LAN peers, DNS rebinding, other sites). Browsers also say who started the request in Sec-Fetch-Site; when it is
 * present only this app's own pages ("same-origin") and direct navigation ("none") pass, so a page on another site
 * or another local port is refused.
 */
export function isLocalRequest(headers: Headers, trusted: Set<string> = trustedHostnames()): boolean {
  const host = headers.get("host");
  const origin = headers.get("origin");
  const fetchSite = headers.get("sec-fetch-site");
  if (fetchSite !== null && !OWN_PAGES.has(fetchSite)) return false;
  if (!host || !trusted.has(hostnameOf(host) ?? "")) return false;
  if (origin && !trusted.has(hostnameOf(origin) ?? "")) return false;
  return true;
}
