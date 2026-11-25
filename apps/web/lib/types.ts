export type RecordOut = {
  id: number; date: string | null; date_suspect: boolean; title: string; record_type: string;
  clinic: string | null; medications: string[]; has_labs: boolean; out_of_range_count: number;
  details: string; doctors_note: string; is_demo: boolean; attachment_count: number;
};
export type AttachmentOut = { id: number; filename: string; mime_type: string; size_bytes: number; is_image: boolean };
export type MarkerSummary = {
  marker_key: string; display_name: string; unit: string; count: number; latest_value: number | null;
  latest_date: string; latest_text: string | null; ref_min: number | null; ref_max: number | null;
  out_of_range_latest: boolean; spark: number[]; is_demo: boolean;
};
export type HistoryPoint = {
  date: string; value: number; ref_min: number | null; ref_max: number | null; out_of_range: boolean;
  date_suspect: boolean; unit: string; is_demo: boolean;
};
export type Delta = { from_date: string; to_date: string; abs: number; pct: number | null; toward_range: boolean | null; stayed_in_range: boolean };
export type MarkerHistory = {
  marker_key: string; display_name: string; unit: string; points: HistoryPoint[]; deltas: Delta[];
  unit_mismatch: boolean; range_mismatch: boolean; enough_data: boolean; text_results: { date: string; text: string }[];
};
export type TierName = "deficient" | "insufficient" | "normal" | "high" | "toxic";
export type MarkerTier = { tier: TierName; min: number | null; max: number | null; label: string; unit?: string; report_id?: number | null };
/** Fields the history endpoint adds on top of MarkerHistory; every one may be absent (older API). */
export type MarkerHistoryExtras = { system?: string; retest_days?: number | null; tiers?: MarkerTier[] };
export type Context = {
  medications: { name: string; dosage: string; start: string; end: string | null }[];
  records: { id: number; date: string; title: string; record_type: string; is_demo: boolean }[];
};
export type DraftRow = {
  name: string; value: number | null; unit: string; ref_min: number | null; ref_max: number | null;
  result_text: string | null; marker_key: string; display_name: string; mapped: boolean; is_out_of_range: boolean;
  needs_profile?: NeedsProfile | null;
};
export type UploadDraft = { file_hash: string; test_date: string | null; lab_name: string; rows: DraftRow[] };
export type SavedLabs = { report_id: number; created: boolean; markers: { marker_key: string; display_name: string }[] };
export type ImagingStudy = {
  id: number; study_date: string; study_type: string; body_part: string; summary_text: string; findings_text: string;
  series_description: string; slice_count: number; frame_count: number;
};
export type UploadedStudy = ImagingStudy & { warnings: string[] };
export type ReportDraft = { summary_text: string; findings_text: string };
export type Preset = { item_name: string; dosage: number | null; unit: string; category: "stimulant" | "supplement" | "medication"; half_life_hours: number | null };
export type SupplementLog = { id: number; timestamp: string; item_name: string; dosage: number | null; unit: string; category: string; half_life_hours: number | null };
export type BedtimeReadout = { bedtime: string; items: { item_name: string; unit: string; remaining: number }[] };
export type JournalCategory = "symptom" | "doctor_visit" | "note";
export type JournalEntry = {
  id: number; entry_date: string; category: JournalCategory; title: string; description: string;
  severity_1_10: number | null; body_location: string | null;
};
export type CnsTest = { id: number; timestamp: string; tap_count_10s: number; baseline_dev_pct: number | null; baseline_mean: number | null; baseline_samples: number };
export type UserSettings = {
  latitude: number | null; longitude: number | null; bedtime: string; timezone: string; ai_briefing: boolean; detected_timezone: string;
};
export type EnvironmentReading = {
  id: number; timestamp: string; aqi: number | null; pm2_5: number | null; pm10: number | null;
  pressure_mmHg: number | null; pressure_delta_24h: number | null; humidity: number | null;
};
export type GraphNodeKind = "symptom" | "trigger" | "biomarker" | "protector";
export type GraphNode = { id: string; label: string; kind: GraphNodeKind; detail: string };
export type Effect = "worsens" | "improves" | "unclear";
export type GraphEdge = {
  id: string; source: string; target: string; r: number; strength: number; lag_hours: number; lag_label: string;
  lagged: boolean; p_value: number; n_days: number; phrase: string; effect: Effect;
};
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[]; notes: string[] };
export type RiskFactor = {
  key: string; label: string; weight: number; points: number; detail: string; has_data: boolean; seen_in_days: number | null;
};
export type Risk = {
  score: number | null; level: "low" | "moderate" | "high" | null; alert: boolean; reason: string;
  factors: RiskFactor[]; recommendations: string[];
};
export type Briefing = {
  date: string; source: "ai" | "fallback"; label: string; bullets: string[]; ai_enabled: boolean; can_retry: boolean;
};
export type DemoStatus = { demo: boolean; counts: Record<string, number> };

// overview-ui: /biomarkers items as the overview reads them; the extra fields may be absent on an older API.
export type OverviewMarker = MarkerSummary & { system?: string; tiers?: unknown[]; age_days?: number; retest_days?: number | null };

// biomarkers-ui: the fields /biomarkers and /biomarkers/{key}/history now always return.
export type Tier = MarkerTier;
export type MarkerSummaryFull = MarkerSummary & { system: string; tiers: Tier[]; age_days: number; retest_days: number | null; needs_profile?: NeedsProfile | null };
export type MarkerHistoryFull = MarkerHistory & { system: string; tiers: Tier[]; retest_days: number | null };

// courses-ui: /freshness and /courses contracts.
export type FreshnessStatus = "fresh" | "due" | "overdue";
export type FreshnessItem = {
  marker_key: string; display_name: string; system: string; last_date: string; age_days: number; retest_days: number | null;
  interval_source: "default" | "custom"; status: FreshnessStatus; due_in_days: number | null; reason: "interval" | "course"; course_id: number | null;
};
export type Freshness = { today: string; items: FreshnessItem[] };
export type CourseStatus = "planned" | "active" | "finished" | "undated";
export type Course = {
  id: number; name: string; dosage: string; start_date: string | null; end_date: string | null; days: number | null; status: CourseStatus;
  ends_in_days: number | null; target_marker_key: string | null; target_marker_name: string | null; notes: string; source: string; editable: boolean;
};
export type CourseInput = {
  name?: string; dosage?: string; start_date?: string; days?: number | null; end_date?: string | null; target_marker_key?: string | null; notes?: string;
};
export type CourseEffect = {
  course_id: number; marker_key: string; display_name: string; unit: string; before: { date: string; value: number; unit?: string } | null; after: { date: string; value: number; unit?: string } | null;
  delta_abs: number | null; delta_pct: number | null; toward_range: boolean | null; days_between: number | null;
  state: "waiting_for_retest" | "no_baseline" | "measured" | "unit_mismatch"; retest_due_date: string | null; note: string;
  stayed_in_range?: boolean | null;
};

// --- Profile (goal 8) ---
export type ProfileSex = "female" | "male";
export type BmiCategory = "underweight" | "normal" | "overweight" | "obese_1" | "obese_2" | "obese_3";
export type BmiStatus = "ok" | "needs_height" | "needs_weight" | "needs_birth_date" | "adult_only";
export type NeedsProfile = "sex" | "age" | "both";
export type Profile = {
  birth_date: string | null; age_years: number | null; sex: ProfileSex | null; height_cm: number | null;
  latest_weight: { date: string; kg: number } | null; latest_waist: { date: string; cm: number } | null;
  bmi: { value: number; category: BmiCategory; date: string } | null; bmi_status: BmiStatus; whtr: number | null;
};
export type ProfileInput = { birth_date?: string | null; sex?: ProfileSex | null; height_cm?: number | null };
export type MeasurementKind = "weight" | "waist";
export type Measurement = { id: number; date: string; kind: MeasurementKind; value: number };
export type BmiBandKey = "underweight" | "normal" | "overweight" | "obese";
export type BmiHistory = {
  height_cm: number | null; bmi_status?: BmiStatus;
  points: { date: string; weight_kg: number; bmi: number; category: BmiCategory }[];
  bands: { key: BmiBandKey; min: number | null; max: number | null }[];
  note: string;
};

// --- Body data from scales (import) ---
export type BodyKind = "weight" | "waist" | "body_fat_pct" | "muscle_kg" | "body_water_pct" | "bone_kg" | "visceral_fat" | "bmr_kcal"
  | "skeletal_muscle_kg" | "skeletal_muscle_pct" | "protein_pct" | "body_age"
  | "hip" | "fat_mass_kg" | "lean_mass_kg" | "active_cell_mass_kg" | "active_cell_mass_pct" | "total_body_water_kg" | "extracellular_water_kg" | "ecw_icw_ratio" | "phase_angle" | "specific_bmr";
export type BodyMeasurement = { id: number; date: string; kind: BodyKind; value: number };
export type BodyPoint = { date: string; value: number };
export type BodySnapshot = { latest: Partial<Record<BodyKind, BodyPoint>>; previous: Partial<Record<BodyKind, BodyPoint>> };
export type ScaleImportResult = {
  delimiter: string; encoding: string;
  columns: { header: string; mapped_to: BodyKind | "date" | null }[];
  day_first: boolean;
  rows: { date: string; values: Partial<Record<BodyKind, number>> }[];
  total_rows: number; imported: number; replaced: number; would_replace?: number; would_replace_days?: number; replaced_days?: number; skipped_total?: number;
  skipped: { line: number; reason: string }[];
  warnings: string[];
};

// Visits and hospital stays (goal 9)
export type RecordKind = "visit" | "hospital_stay" | "procedure" | "lab" | "imaging" | "other";
export type StayStatus = "ongoing" | "completed";
export type DiagnosisStatus = "suspected" | "confirmed" | "ruled_out";
export type DiagnosisIn = { name: string; icd10?: string | null; status?: DiagnosisStatus; note?: string | null };
export type Diagnosis = { id: number; name: string; icd10: string | null; status: DiagnosisStatus | null; note: string | null };
export type TreatmentIn = { name: string; dosage?: string | null; route?: string | null; frequency?: string | null; start_date?: string | null; end_date?: string | null; notes?: string | null };
export type RecordTreatment = {
  id: number; name: string; dosage: string | null; route: string | null; frequency: string | null;
  start_date: string | null; end_date: string | null; notes: string | null; status: "planned" | "active" | "finished" | "undated"; editable: boolean;
};
export type RecordNote = { id: number; date: string | null; text: string; kind: "note" | "question"; done: boolean };
export type RecordInput = {
  record_type: RecordKind; title: string; date?: string | null; end_date?: string | null; status?: StayStatus;
  clinic_name?: string | null; department?: string | null; doctor_name?: string | null; reason?: string | null;
  details?: string | null; doctors_note?: string | null; diagnoses?: DiagnosisIn[]; treatments?: TreatmentIn[]; questions?: string[];
};
/** Fields added to list items; every one may be absent when the API is older. */
export type RecordItemExtras = { end_date?: string | null; status?: StayStatus | null; stay_days?: number | null; diagnoses?: string[]; diagnosis_items?: { name: string; status: DiagnosisStatus | null }[]; is_manual?: boolean; organs?: { key: string; name: string }[] };
export type RecordItem = RecordOut & RecordItemExtras;
export type RecordDetail = RecordOut & {
  end_date: string | null; status: StayStatus | null; department: string | null; doctor_name: string | null; reason: string | null;
  stay_days: number | null; is_manual: boolean; diagnoses: Diagnosis[]; treatments: RecordTreatment[]; notes: RecordNote[]; attachments: AttachmentOut[];
};

export type ChatActionStatus = "pending" | "done" | "dismissed" | "failed";
export type ChatAction = { id: string; name: string; label: string; status: ChatActionStatus; result: string };
export type ChatUsage = { input_tokens: number; cached_tokens: number; output_tokens: number };
export type ChatAnswer = {
  answer: string;
  usage: ChatUsage;
  thread_id?: number;
  message_id?: number;
  actions?: ChatAction[];
};
export type ChatThreadSummary = {
  id: number;
  title: string;
  channel: string;
  updated_at: string;
  message_count: number;
};
export type ChatMessageItem = {
  id: number;
  role: "user" | "model";
  text: string;
  image_url: string | null;
  actions: ChatAction[];
  created_at: string;
};
export type ChatThreadDetail = {
  id: number;
  title: string;
  channel: string;
  messages: ChatMessageItem[];
};

// --- Organ history (ultrasound-style scans grouped by organ) ---
export type ScanOrigin = "rule" | "ai" | "manual";
export type ScanSide = "" | "left" | "right";
export type Headline = {
  series_key: string; name: string; unit: string; value: number; previous: number | null;
  delta: number | null; pct: number | null;
};
export type OrganSummary = {
  key: string; name: string; scan_count: number; latest_date: string | null; unverified_count: number; headline: Headline | null;
};
export type OrganIndex = {
  organs: OrganSummary[];
  unassigned: { record_id: number; date: string | null; title: string }[];
};
export type ScanValue = {
  value: number | null; value_text: string | null; unit: string; origin: ScanOrigin; verified: boolean;
  change: { delta: number | null; pct: number | null; direction: "up" | "down" | "same" | "changed" } | null;
};
export type ScanColumn = {
  record_id: number; date: string | null; date_suspect: boolean; title: string; details: string | null;
  doctors_note: string | null; body_markdown: string | null;
  attachments: { id: number; filename: string; mime_type: string }[];
  has_numbers: boolean; values: Record<string, ScanValue>;
};
export type OrganSeries = {
  series_key: string; name: string; unit: string; points: { record_id: number; date: string; value: number | null }[];
};
export type Treatment = { name: string; dosage: string | null; start: string; end: string | null; related: boolean };
export type VisitRef = { id: number; date: string; title: string; record_type: string };
export type OrganDetail = {
  key: string; name: string; aliases: string[]; related_marker_keys: string[];
  params: { series_key: string; param_key: string; side: ScanSide; name: string; unit: string; kind: "numeric" | "text"; chart: boolean; headline: boolean }[];
  scans: ScanColumn[]; series: OrganSeries[]; treatments: Treatment[]; visits: VisitRef[];
};
export type ScanMeasurementRow = {
  organ_key: string; param_key: string; name: string; side: ScanSide; value: number | null; value_text: string | null;
  unit: string; origin: ScanOrigin; verified: boolean;
};
export type ScanTags = {
  record_id: number; organs: { organ_key: string; name: string; origin: ScanOrigin }[]; measurements: ScanMeasurementRow[];
};
export type ScanExtractReport = { added: number; updated: number; skipped_verified: number; organs_added: string[] };
export type ScanExtractResult = ScanTags & { report: ScanExtractReport; ai_report: ScanExtractReport | null };
export type OrganCatalogEntry = {
  key: string; name: string;
  params: { key: string; name: string; kind: "numeric" | "text"; unit: string; sides: boolean }[];
};

// --- Body signals: Samsung Health import (mirrors routers/imports.py JobOut and samsung_import summary) ---
export type ImportJobStatus = "queued" | "running" | "done" | "failed";
export type ImportStage = "" | "parse" | "derive" | "sleep" | "workouts" | "daily" | "done";
export type SamsungImportSummary = {
  counts: Record<string, number>; // record list (sleep, stages, hrv, skin, resp, spo2, hr, steps, stress, workouts, body) -> records read
  skipped: Record<string, string>; // export type -> reason ("not imported" or "missing column(s): …")
  junk: Record<string, number>; // export type -> unreadable rows dropped
  days: number; nights: number;
  workouts: { added: number; updated: number; unchanged: number };
  dropped_workouts: number; body: number; latest_height_cm: number | null;
};
export type ImportJob = {
  id: number; status: ImportJobStatus; progress: number; stage: ImportStage | string;
  summary: Partial<SamsungImportSummary>; // {} until the job is done
  error: string | null; started_at: string | null; finished_at: string | null;
};
export type ImportStarted = { job_id: number };

// --- Body signals: read model (mirrors services/signals.py overview) ---
export type SignalTileKey = "sleep_total_min" | "resting_hr" | "hrv_sdnn" | "skin_temp_delta" | "spo2_avg" | "steps" | "weight";
export type SignalBand = { p25: number; p75: number };
export type SignalPosition = "below" | "within" | "above";
export type SignalPoint = { date: string; value: number };
export type SignalTile = {
  key: SignalTileKey; name: string; unit: string; value: number | null; date: string | null;
  spark: SignalPoint[]; band: SignalBand | null; position: SignalPosition | null;
  partial: boolean; // the day is cut off (the export's last day, or today): shown without a position
};
/** How old the watch data is. `today` is the API's (configured zone); `as_of` the data's last day; `stale` when that
 *  is more than 7 days back — then "recent" windows end on as_of, and pages say so instead of "now" or "last night". */
export type SignalFreshness = { today: string; as_of: string | null; stale: boolean };
export type SleepStageMinutes = { deep: number; rem: number; light: number; awake: number };
export type LastNight = {
  session_id: number; wake_date: string; start_local: string; end_local: string; duration_min: number;
  stages: SleepStageMinutes;
};
export type SignalsOverview = SignalFreshness & {
  tiles: SignalTile[]; last_night: LastNight | null; has_data: boolean; short_sleep_end: string | null;
  latest_import: { finished_at: string | null; summary: Partial<SamsungImportSummary> } | null; // finished_at: UTC, +00:00
};

// --- Body signals: sleep page (mirrors services/signals.sleep_list / sleep_detail) ---
/** One night, keyed by the local wake-up date. Local times are naive ISO strings (no zone): show them as written. */
export type SleepNight = {
  session_id: number; wake_date: string; start_local: string; end_local: string; duration_min: number;
  deep: number; rem: number; light: number; awake: number; efficiency: number | null; parts: number;
};
export type SleepWindow = {
  nights: number; duration_min: number | null; deep: number | null; rem: number | null; light: number | null;
  awake: number | null; efficiency: number | null;
};
export type SleepList = SignalFreshness & {
  nights: SleepNight[]; // newest first
  summary: { last30: SleepWindow; prev30: SleepWindow; change: Omit<SleepWindow, "nights"> };
};
export type SleepStageName = "awake" | "light" | "deep" | "rem";
export type SleepStageSpan = { start_local: string; end_local: string; stage: SleepStageName };
export type SleepDetail = { session: SleepNight & { is_main: boolean }; stages: SleepStageSpan[] };

// --- Body signals: series and workouts (mirrors services/signals.series / workouts) ---
export type SignalSeries = {
  name: string; unit: string; points: SignalPoint[]; band: SignalBand | null; position: SignalPosition | null;
  partial: boolean; // the last point is a cut-off day (see SignalTile.partial)
};
export type SignalSeriesMap = SignalFreshness & { series: Record<string, SignalSeries> };
export type WorkoutItem = {
  id: number; local_date: string; start_local: string; type_code: number; type_name: string; duration_min: number;
  kcal: number | null; distance_m: number | null; hr_avg: number | null; hr_max: number | null;
};
export type WorkoutType = { type_code: number; type_name: string; count: number };
export type WorkoutList = { items: WorkoutItem[]; types: WorkoutType[] };
