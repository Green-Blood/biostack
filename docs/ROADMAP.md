# BioStack Roadmap & Open-Source Release Plan

This document tracks what was recently shipped for the open-source release, remaining future features, polish items, and the final launch checklist.

---

## Recently Completed

- **Pluggable AI providers (Gemini + OpenAI-compatible)**: Support for `AI_PROVIDER=openai_compat` (Ollama, LM Studio, OpenAI, OpenRouter) alongside Google Gemini, plus AI status and connection test (`GET /api/v1/settings/ai-status`, `POST /api/v1/settings/ai-test`) in **Settings**.
- **First-run onboarding wizard**: Guided 3-step getting-started card on the **Overview** page when no records exist yet.
- **Apple Health ZIP importer**: Streaming `export.xml` ZIP parser (`POST /api/v1/imports/apple-health`) and upload card in **Settings** covering steps, distance, active energy, resting HR, HRV (SDNN), SpO2, and sleep stages.
- **Doctor Visit Pack (`/doctor`)**: Printable clinical summary page combining age/sex/BMI snapshot, out-of-range biomarkers, active courses, recent visits/records, and organ scan counts.
- **Optional access password gate (`BIOSTACK_ACCESS_PASSWORD`)**: Built-in `HttpOnly` HMAC-signed session login screen and `/api/*` proxy guard (while keeping `X-API-Key` phone health sync working).

---

## Planned Future Features

1. **In-App AI Provider & Model Editor**
   - Allow editing provider settings and fetching live available model lists directly from the Settings UI (today configured via `.env`).
2. **Additional Wearable Importers**
   - **Garmin**, **Oura**, and a generic **CSV/JSON** wearable importer.
3. **Multi-Profile / Family Support**
   - Allow managing separate health records for family members (children, parents, partner) within a single self-hosted instance.
4. **Merge-Style ZIP Import**
   - Support merging a BioStack export ZIP into an existing database (currently ZIP restore targets an empty database only).

---

## Polish & Known Items

- **Theme QA pass**: Audit all 6 themes across every page and chart for contrast and edge-case styling.
- **Samsung Health import**:
  - Localize skipped-row reasons in the import summary (currently English-only).
  - Have a native Russian speaker review workout names and handle unknown workout codes gracefully.
  - Clarify total body water units in Samsung exports and enable import once verified.
- **Bioimpedance reference ranges**: Store per-kind reference ranges printed directly on body-composition reports.
- **Biomarkers list cleanup**: Hide or group noisy urine-microscopy rows so core markers stay easy to scan.
- **Reference range edge tests**: Expand test coverage around sex/age boundary transitions when picking lab ranges.
- **Live integration smoke tests**: Verify Open-Meteo environment refresh, real Telegram bot flow, and Gemini voice-note transcription against live services (currently covered with fakes in unit tests).
- **Off-site encrypted backups**: Implement automated off-site backup sync as designed in [`docs/BACKUPS-OFFSITE.md`](BACKUPS-OFFSITE.md).

---

## Public Launch Checklist

- [x] Capture clean screenshots using synthetic showcase data and place them in `docs/screenshots/` for `README.md`.
- [x] Export the clean tree with `./scripts/export_public.sh <dest-dir>`.
- [x] Run a secret scan (`gitleaks detect --no-git --source <dest-dir>`).
- [x] Verify the exported tree passes lint and typecheck cleanly.
- [ ] Initialize a fresh Git repository in `<dest-dir>` with clean author metadata and push to the public GitHub repository so CI runs on `main`.
