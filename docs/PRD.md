# BioStack — Master PRD (owner's original, condensed but complete)

Autonomous, self-hosted, predictive AI health management system / biomarker OS. Unifies lab PDFs, DICOM imaging, wearable telemetry, NFC/1-tap supplement logs, environment, CNS readiness tests and a journal. Lag-correlation analysis finds root causes of physiological drops, projects early-warning risk, with a Next.js PWA and (phase 2) a Telegram bot with local voice transcription.

## Original stack (see the design doc for what was changed)
Next.js 15 / React 19 / Tailwind v4 / shadcn/ui / Tremor / `@xyflow/react` / Recharts, PWA. FastAPI, SQLModel, Uvicorn, Polars/NumPy. SQLite `biostack.db`, local `/data/pdf/`, `/data/imaging/`. `google-genai` (Gemini Flash/Vision) with optional DeepSeek/Ollama fallback; Faster-Whisper; pydicom + PIL; Aiogram 3.x webhook; Tailscale, Docker Compose, static bearer token `API_SECRET_KEY`.

## Layout
`apps/api` (main.py, config.py, db/{database,models}.py, routers/{health,labs,imaging,metrics,supplements,environment,journal,analytics,telegram}.py, services/{gemini_parser,whisper_stt,dicom_processor,half_life_engine,environment_cron,lag_analyzer,early_warning,context_builder}.py) and `apps/web` (app/{page,biomarkers,imaging,graph,journal,settings}, components/{ui,dashboard,graph}), `data/{imaging,pdf}`, docker-compose.yml, .env.example.

## Schema
- LabReport: id, test_date (YYYY-MM-DD), lab_name, pdf_path, created_at
- Biomarker: id, report_id FK, marker_key (e.g. vitamin_d_25_oh), display_name, value float, unit, ref_min, ref_max, is_out_of_range
- ImagingStudy: id, study_date, study_type (MRI/CT/Ultrasound), body_part, summary_text, findings JSON, zip_path, keyframe_paths JSON array
- DailyMetric: metric_date PK, resting_hr, hrv_sdnn, sleep_total_min, sleep_deep_min, sleep_rem_min, steps, vo2_max, skin_temp_delta
- SupplementLog: id, timestamp, item_name, dosage, unit, category (stimulant/supplement/medication), half_life_hours
- EnvironmentalLog: id, timestamp, aqi, pm2_5, pm10, pressure_mmHg, pressure_delta_24h, humidity
- HealthJournal: id, entry_date, category (symptom/doctor_visit/note), title, description, severity_1_10 optional, body_location
- CnsTest: id, timestamp, tap_count_10s, baseline_dev_pct
- CorrelationCache: id, target_metric, trigger_key, correlation_score float, lag_hours int, confidence_pct, last_updated

## Modules
1. **Lab parser:** PDF upload (UI/Telegram) → Gemini with strict JSON schema, normalized snake_case keys (ferritin, testosterone_total); auto range check (value<ref_min or >ref_max); store LabReport + Biomarker.
2. **DICOM/imaging:** ZIP of .dcm stored at /data/imaging/{study_id}/; Gemini Vision/OCR extracts the text report → diagnosis & findings; pydicom extracts 3–5 high-contrast keyframe slices as PNG, shown in UI and supplied to Gemini for secondary visual queries.
3. **Wearables webhook** `/api/v1/health-sync`: POST from iOS Health Auto Export / Android Tasker; `X-API-Key` auth; upsert into DailyMetric.
4. **Supplements + half-life:** instant logging (iOS Shortcuts/NFC/UI quick-tap, e.g. "Caffeine 200mg 16:30"); remaining concentration at bedtime (23:00) `C(t)=C0·0.5^(t/t½)` correlated with sleep fragmentation.
5. **Environment cron:** every 3h fetch AQI, PM2.5, PM10, pressure, humidity (Open-Meteo/IQAir); compute 24h pressure delta.
6. **CNS readiness:** 10-second finger-tapping canvas test vs 14-day rolling baseline (baseline_dev_pct); Mental Load Index via evening 1–5 check-in or screen-time ingestion.
7. **Journal:** symptoms, doctor visit notes, medications, discomfort, severity 1–10, body location.
8. **Lag analyzer:** Pearson/Spearman between targets (HRV drop, deep sleep loss, symptom severity) and lagged predictors (mental load, caffeine at 23:00, PM2.5, heavy axial workouts); lags 0/+12/+24/+36/+48h; cache pairs with p<0.05 and |r|>0.5.
9. **React Flow graph:** nodes — 🔴 symptoms/drops, 🟡 triggers/behaviors, 🔵 biomarkers, 🟢 protectors; edge thickness = |r|; dashed = lagged (+24h/48h); node click = Focus Mode (dim unrelated, isolate immediate precursors).
10. **Early warning:** daily Predictive Risk Score 0–100% from last 48h + forecasts + lag correlations; >70% → high-priority alert with preventive recommendations (e.g. deload, 500mg magnesium, sleep before 23:00).
11. **Daily briefing:** on dashboard load, trailing-72h window across all tables → dense JSON → Gemini → 3 bullets (state of day, discovered lag correlations, preventive steps).
12. **Telegram bot (phase 2):** TELEGRAM_USER_ID whitelist; .ogg voice → Faster-Whisper; LLM intent router (LOG_SYMPTOM, LOG_INGESTION, LOG_ACTIVITY, QUERY_AI); photo of medical paper → Gemini Vision with user confirmation before DB commit; inline keyboards for CNS check-ins, /status, PNG graph.
