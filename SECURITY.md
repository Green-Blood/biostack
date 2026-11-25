# Security & Privacy Policy

## Threat Model & Design

BioStack is a **single-user, self-hosted** personal health workspace:

- Local runs bind to `127.0.0.1` only.
- The Next.js proxy checks `Host`, `Origin`, and `Sec-Fetch-Site` headers against `localhost` and `ALLOWED_HOSTS` (`apps/web/lib/local-guard.ts`).
- Server deployments are intended to run behind a private network such as Tailscale (`docs/SERVER.md`), not exposed directly to the public internet without additional authentication.
- AI features are **opt-in**:
  - Lab PDFs with recognizable tables can be parsed locally without AI.
  - Scan/imaging reports sent to Gemini are uploaded once after confirmation and cached by content hash.
  - **Ask the AI** sends your serialized medical record context to the configured Gemini model on each query. Do not configure `GEMINI_API_KEY` if you do not want your records sent to Google's API.

## Reporting a Vulnerability

If you discover a security vulnerability (for example: host/origin guard bypass, path traversal in file/ZIP import or attachments, SQL injection, or credential leakage):

1. **Please do not open a public GitHub issue** with exploit details.
2. Report it privately using GitHub Security Advisories (**Security -> Advisories -> Report a vulnerability**) on the repository.
3. Include steps to reproduce, affected files/endpoints, and potential impact.

We will acknowledge reports promptly and work on a fix before public disclosure.
