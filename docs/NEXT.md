# What is next

State on 2026-11-12: phase 1 (local-only) is complete. Phase 2 (server, Telegram bot) is built on branch `build/phase2-server` and running on the home server; see `docs/SERVER.md`.

## Done in phase 1

Notion import, timeline, biomarkers by body system with range tiers, time charts, freshness and courses, profile with BMI and scale data, visits and hospital stays, files inbox, global search, six themes, Russian and English, one-click ZIP export, **Ask the AI** (whole record as cached text, optional photo, token usage).

## Done: organ history

Organs pages built from ultrasounds: organ tags and measurements per record (read by rules, editable on the record page), an index at `/organs`, per-organ charts, change table and conclusions, a doctor view, organ names in search, organ chips on the timeline, and `scripts.backfill_scans` for existing records. Checking the automatic numbers against the original reports is the owner's step.

## Done: Samsung Health import and body signals

Import of the Samsung Health export (Settings card with upload progress, or `python -m scripts.import_samsung_health`), idempotent and never replacing manual values. Pages `/signals`, `/signals/sleep`, `/signals/heart`, `/signals/activity` with each number against your usual band, a strip on the Overview and search entries. Dry-run on copies of the real database and a real 72 MB export found one misread (skeletal muscle mass mapped to total muscle), now fixed.

## Done in phase 2

Docker Compose stack (API, web, bot), Tailscale HTTPS access, one-command deploy with backup and rollback, nightly backups (14 kept), restore script, owner-only Telegram bot (text, photo, voice note, `/today`, `/export`), voice-note transcription endpoint, configurable trusted hostnames for the web proxy, phone health sync through the proxy.

## Still to do for phase 2

- Create the Telegram bot with @BotFather and put the token and your id in the server's `.env` (steps in `docs/SERVER.md`). Until then the bot stays off.
- Try voice notes and photos against the real services; both are tested against fakes only.
- Copy `state/backups/` off the server now and then; backups on the same disk do not survive losing the machine.
- Merge `build/phase2-server` into `main` when you are happy with it.

## Done: sync, chat, body data

- **Automatic sync** from the phone (Health Connect Webhook app on `/health-sync`, records stored by id so resends never double count) is working.
- **Ask the AI** is a saved multi-turn chat with photos, Telegram threads and confirmable actions. Answers now cite the record rows they used, and the web panel streams the answer as it is written (`POST /chat/ask-stream`, newline-delimited JSON; `/chat/ask` stays for the Telegram bot).
- **Body data**: skeletal muscle (kg and %), protein % and body age are stored kinds (body age is the scale's estimate, not a medical value). Derived values (fat kg, water kg, lean mass) are not stored; they are not shown until someone needs them. Samsung `skeletal_muscle_mass` and `skeletal_muscle` now map to their own kinds, so the old muscle-chart clash is gone. Total body water is still not read (unit unclear).

## Done: data in and out

- **Import a BioStack ZIP back**: Settings, "Restore from a BioStack ZIP" (`POST /settings/import/archive`). Restores every table and the files into an **empty** database only (lost machine or fresh install); it refuses when data exists and never merges. The export carries `data/files-manifest.json` so files go back where they belong; ZIPs from before this change restore the tables but not the files.
- **DICOM in the ZIP**: optional checkbox on export (`?include_dicom=true`); scan key frames are always included.
- **HEIC preview**: HEIC attachments and chat photos are converted to JPEG when shown (`pillow-heif`); `?original=true` on the attachment URL gives the HEIC itself.
- Body data from bioimpedance reports: fat/lean/active cell mass, total and extracellular water, water ratio, phase angle, specific BMR and hip are stored kinds. Ranges printed on the report are not stored yet.

## Next up

Nothing queued. Candidates: store the per-kind reference range printed on body-composition reports; merge-style import; the minor items below.

## Known minor items

- Samsung import: the "skipped" reasons in the import summary are English only.
- Samsung import: the Russian workout names are not checked by a native speaker, and a workout code that is not in the list shows as "Workout (code N)".
- Samsung import: total body water is not read (unit unclear).
- Organ history: numbers read automatically stay marked "?" until you verify them; the extractor covers the 8 catalog organs and common wording only, so unusual report phrasing may need a manual entry.
- Hide the 11 urine-microscopy rows that clutter the biomarkers list.
- Age boundaries in sex/age range picking are tested at the obvious edges only.
- Only some of the six themes were checked by eye on every page.
- `GEMINI_MODEL` has no validation until the first call; a retired model name returns 404 from Google.

## Open-source checklist (do before making the repo public)

The repository is private now. Before it is public:

1. **History**: the commit history contains the owner's name/email in the git author field and earlier versions of the spec docs that quoted personal details (a hospital stay, real lab trends). HEAD was cleaned, history was not. Either publish a fresh repository from a squashed, reviewed tree (simplest) or rewrite history with `git filter-repo`. Do not just flip the visibility switch.
2. **Secrets**: rotate the Gemini key if it was ever pasted anywhere outside `.env`. `.env`, `*.db`, `data/` and `.playwright-mcp/` are git-ignored; keep it that way. Run a secret scan (for example `gitleaks`) over the final tree.
3. **Real data**: confirm nothing in `apps/api/tests`, fixtures or demo seeds comes from the owner's real records (tests use synthetic values). `apps/api/importers/` mentions Notion; keep it as an optional importer with the snapshot format documented.
4. **Docs for strangers**: replace "the owner" with a neutral voice in `docs/`, add screenshots made with demo data (`scripts/seed_demo`), a quick-start that works from a clean clone, and a clear statement that this is not medical advice.
5. **Licence** (none yet; pick MIT or Apache-2.0), `CONTRIBUTING.md`, issue templates, a CI workflow running `pytest`, `tsc`, `eslint` and `next build`.
6. **Privacy defaults**: the app is single-user and local by design; say so loudly, and say that Ask the AI sends the whole record to Google.
