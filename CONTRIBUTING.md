# Contributing to BioStack

Thank you for your interest in contributing to BioStack!

## Development Setup

### Prerequisites
- Python 3.13 + [uv](https://docs.astral.sh/uv/)
- Node.js 22+ + npm

### Local environment
1. Copy `.env.example` to `.env` in the repository root.
2. Create `apps/web/.env.local`:
   ```env
   API_BASE_URL=http://localhost:8000
   API_SECRET_KEY=change-me
   ```
3. Install dependencies:
   ```bash
   cd apps/api && uv sync
   cd apps/web && npm install
   ```
4. Start both servers (API on `:8000`, web on `:3000`):
   ```bash
   ./scripts/dev.sh
   ```

## Running Tests & Checks

Before opening a pull request, verify both packages:

```bash
# Backend tests
cd apps/api && uv run pytest -q

# Frontend typecheck, lint, and production build
cd apps/web && npx tsc --noEmit && npm run lint && npm run build
```

## Coding & Data Guidelines

- **Synthetic test data only**: Never include real medical records, personal PDFs, DICOM files, or identifiable user data in tests, fixtures, seeds, or screenshots. Use synthetic data (see `apps/api/services/demo_data.py` and `apps/api/tests/samsung_fixture.py`).
- **Deterministic math over guesswork**: Charts, range tiers, correlations, and freshness calculations must remain deterministic and explainable. When there is too little data, show that clearly instead of fabricating scores.
- **Bilingual UI (EN & RU)**: Any user-facing UI string belongs in `apps/web/lib/i18n/dictionaries/en/` and `apps/web/lib/i18n/dictionaries/ru/`, and API user messages belong in `apps/api/services/i18n_messages.py`.
- **Keep PRs focused**: Match the existing style and keep changes scoped to the feature or fix.

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Make your changes and add or update tests where appropriate.
3. Ensure `pytest`, `tsc --noEmit`, `npm run lint`, and `npm run build` pass.
4. Open a pull request describing what changed and how you verified it.
