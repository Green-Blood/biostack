import datetime as dt

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def _src_unique(table: str) -> tuple:
    return (UniqueConstraint("source", "external_id", name=f"uq_{table}_source_external"),)


DEMO_SOURCE = "demo"


class Clinic(SQLModel, table=True):
    __table_args__ = _src_unique("clinic")
    id: int | None = Field(default=None, primary_key=True)
    name: str
    source: str = "manual"
    external_id: str | None = None


class MedicalRecord(SQLModel, table=True):
    __table_args__ = _src_unique("medicalrecord")
    id: int | None = Field(default=None, primary_key=True)
    record_date: dt.date | None = Field(default=None, index=True)
    date_suspect: bool = False
    title: str
    record_type: str = "other"  # visit | hospital_stay | procedure | lab | imaging | other
    end_date: dt.date | None = None  # a hospital stay's last day; None while it is ongoing
    status: str | None = None  # hospital stays only: ongoing | completed
    department: str | None = ""
    doctor_name: str | None = ""
    reason: str | None = ""
    clinic_id: int | None = Field(default=None, foreign_key="clinic.id")
    details: str = ""
    doctors_note: str = ""
    body_markdown: str = ""
    source: str = "manual"
    external_id: str | None = None


class Diagnosis(SQLModel, table=True):
    """A diagnosis written down for a record. Private: never part of the AI context."""
    id: int | None = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="medicalrecord.id", index=True)
    name: str
    icd10: str = ""
    status: str = "suspected"  # suspected | confirmed | ruled_out
    note: str = ""


class RecordNote(SQLModel, table=True):
    """A daily note or a question for the doctor (kind "question", ticked off with `done`). Private."""
    id: int | None = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="medicalrecord.id", index=True)
    note_date: dt.date
    text: str
    kind: str = "note"  # note | question
    done: bool = False


class RecordAttachment(SQLModel, table=True):
    """An original file (scan, report, photo) kept with a record. Files live in data/attachments under their hash."""
    __table_args__ = (UniqueConstraint("record_id", "sha256", name="uq_attachment_record_sha256"),)
    id: int | None = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="medicalrecord.id", index=True)
    filename: str
    stored_path: str
    mime_type: str
    size_bytes: int
    sha256: str


class Medication(SQLModel, table=True):
    __table_args__ = _src_unique("medication")
    id: int | None = Field(default=None, primary_key=True)
    name: str
    dosage: str = ""
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    notes: str = ""
    route: str | None = None  # oral | IV | injection ... (treatments entered on a visit)
    frequency: str | None = None
    target_marker_key: str | None = None  # the marker a course is meant to affect
    source: str = "manual"
    external_id: str | None = None


class RecordMedication(SQLModel, table=True):
    record_id: int = Field(foreign_key="medicalrecord.id", primary_key=True)
    medication_id: int = Field(foreign_key="medication.id", primary_key=True)


class LabReport(SQLModel, table=True):
    __table_args__ = _src_unique("labreport")
    id: int | None = Field(default=None, primary_key=True)
    test_date: dt.date = Field(index=True)
    lab_name: str = ""
    pdf_path: str | None = None
    file_hash: str | None = Field(default=None, index=True)
    record_id: int | None = Field(default=None, foreign_key="medicalrecord.id")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    source: str = "manual"
    external_id: str | None = None


class MarkerTier(SQLModel, table=True):
    """One band the lab itself printed under a result (deficient ... toxic), in the marker's own unit."""
    id: int | None = Field(default=None, primary_key=True)
    marker_key: str = Field(index=True)
    tier: str  # deficient | insufficient | normal | high | toxic
    min_value: float | None = None
    max_value: float | None = None
    unit: str = ""
    label: str = ""  # the lab's own wording
    report_id: int | None = Field(default=None, foreign_key="labreport.id")
    source: str = "pdf"


class Biomarker(SQLModel, table=True):
    __table_args__ = _src_unique("biomarker")
    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="labreport.id", index=True)
    marker_key: str = Field(index=True)
    display_name: str
    raw_name: str = ""
    value: float | None = None
    result_text: str | None = None
    comparator: str | None = None
    unit: str = ""
    ref_min: float | None = None
    ref_max: float | None = None
    is_out_of_range: bool = False
    needs_profile: str | None = None  # "sex" | "age" | "both": the range is blank only because the profile lacked this
    source: str = "manual"
    external_id: str | None = None


class ImagingStudy(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    study_date: dt.date
    study_type: str
    body_part: str = ""
    summary_text: str = ""
    findings: dict = Field(default_factory=dict, sa_column=Column(JSON))
    zip_path: str | None = None
    keyframe_paths: list = Field(default_factory=list, sa_column=Column(JSON))
    file_hash: str | None = Field(default=None, unique=True, index=True)
    series_description: str = ""
    slice_count: int = 0


class DailyMetric(SQLModel, table=True):
    metric_date: dt.date = Field(primary_key=True)
    resting_hr: float | None = None
    hrv_sdnn: float | None = None
    sleep_total_min: float | None = None
    sleep_deep_min: float | None = None
    sleep_rem_min: float | None = None
    steps: int | None = None
    vo2_max: float | None = None
    skin_temp_delta: float | None = None
    hrv_rmssd: float | None = None
    sleep_light_min: float | None = None
    sleep_awake_min: float | None = None
    sleep_efficiency: float | None = None
    skin_temp_c: float | None = None
    spo2_avg: float | None = None
    spo2_min: float | None = None
    respiratory_rate: float | None = None
    distance_m: float | None = None
    active_kcal: float | None = None
    stress_avg: float | None = None
    source: str = "manual"  # last writer; field_sources says who wrote each field
    field_sources: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False, server_default="{}"))


class SleepSession(SQLModel, table=True):
    __table_args__ = _src_unique("sleepsession")
    id: int | None = Field(default=None, primary_key=True)
    source: str
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_offset_min: int = 0
    wake_date: dt.date = Field(index=True)  # local date of the wake-up
    duration_min: float = 0
    deep_min: float = 0
    rem_min: float = 0
    light_min: float = 0
    awake_min: float = 0
    efficiency: float | None = None
    sleep_type: str = ""
    is_main: bool = True
    device_id: str = ""


class SleepStage(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("session_id", "external_id", name="uq_sleepstage_session_external"),)
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sleepsession.id", index=True)
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    stage: str  # awake | light | deep | rem


class Workout(SQLModel, table=True):
    __table_args__ = _src_unique("workout")
    id: int | None = Field(default=None, primary_key=True)
    source: str
    external_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    tz_offset_min: int = 0
    local_date: dt.date = Field(index=True)
    type_code: int = 0
    duration_min: float = 0
    kcal: float | None = None
    distance_m: float | None = None
    hr_avg: float | None = None
    hr_max: float | None = None
    device_id: str = ""


class WearableRecord(SQLModel, table=True):
    """One Health Connect record's part of one daily field, kept so a resent or edited record replaces itself."""
    key: str = Field(primary_key=True)  # "<record id>|<field>"
    day: dt.date = Field(index=True)
    field: str
    value: float
    origin: str = ""


class ImportJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str
    status: str = "queued"  # queued | running | done | failed
    progress: float = 0.0  # 0..1
    stage: str = ""
    summary: dict = Field(default_factory=dict, sa_column=Column(JSON))
    error: str | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None


class SupplementLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: dt.datetime = Field(index=True)
    item_name: str
    dosage: float | None = None
    unit: str = ""
    category: str = "supplement"  # stimulant | supplement | medication
    half_life_hours: float | None = None
    source: str = "manual"


class EnvironmentalLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: dt.datetime = Field(index=True)
    aqi: float | None = None
    pm2_5: float | None = None
    pm10: float | None = None
    pressure_mmHg: float | None = None
    pressure_delta_24h: float | None = None
    humidity: float | None = None
    source: str = "manual"


class HealthJournal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    entry_date: dt.date = Field(index=True)
    category: str = "note"  # symptom | doctor_visit | note
    title: str
    description: str = ""
    severity_1_10: int | None = None
    body_location: str | None = None
    source: str = "manual"


class CnsTest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: dt.datetime = Field(index=True)
    tap_count_10s: int
    baseline_dev_pct: float | None = None
    source: str = "manual"


class CorrelationCache(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    target_metric: str
    trigger_key: str
    correlation_score: float
    lag_hours: int
    confidence_pct: float
    p_value: float = 1.0
    spearman_score: float = 0.0
    spearman_p: float = 1.0
    n_days: int = 0
    last_updated: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class BriefingCache(SQLModel, table=True):
    briefing_date: dt.date = Field(primary_key=True)
    bullets: list = Field(default_factory=list, sa_column=Column(JSON))
    generated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    source: str = "real"
    failed: bool = False


class MarkerAlias(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    raw_name: str = Field(unique=True, index=True)
    marker_key: str
    display_name: str


class DateReview(SQLModel, table=True):
    record_id: int = Field(foreign_key="medicalrecord.id", primary_key=True)
    confirmed_date: dt.date | None = None


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict | list = Field(default_factory=dict, sa_column=Column(JSON))


class Profile(SQLModel, table=True):
    """The owner's few body facts (one row, id 1). Used to pick the right printed reference range and for BMI."""
    id: int = Field(default=1, primary_key=True)
    birth_date: dt.date | None = None
    sex: str | None = None  # female | male
    height_cm: float | None = None
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class BodyMeasurement(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("measured_on", "kind", name="uq_bodymeasurement_day_kind"),)
    id: int | None = Field(default=None, primary_key=True)
    measured_on: dt.date = Field(index=True)
    kind: str  # weight (kg) | waist (cm)
    value: float
    source: str = "manual"


class RecordOrgan(SQLModel, table=True):
    """Which organs a record (an ultrasound, a visit) mentions. origin: rule | ai | manual."""
    record_id: int = Field(foreign_key="medicalrecord.id", primary_key=True)
    organ_key: str = Field(primary_key=True)
    origin: str = "rule"


class ScanMeasurement(SQLModel, table=True):
    """One measured or described parameter of an organ on a record. side is "" (not NULL) when the parameter has no
    sides, so the unique constraint works in SQLite. origin: rule | ai | manual."""
    __table_args__ = (UniqueConstraint("record_id", "organ_key", "param_key", "side",
                                       name="uq_scanmeasurement_record_organ_param_side"),)
    id: int | None = Field(default=None, primary_key=True)
    record_id: int = Field(foreign_key="medicalrecord.id", index=True)
    organ_key: str
    param_key: str
    side: str = ""  # "" | left | right
    value: float | None = None
    value_text: str | None = None
    unit: str = ""
    origin: str = "rule"
    verified: bool = False


class ChatThread(SQLModel, table=True):
    """One conversation with the AI, kept so a follow-up question has what came before."""
    id: int | None = Field(default=None, primary_key=True)
    title: str = ""
    channel: str = "web"  # web | telegram
    external_id: str | None = Field(default=None, index=True)  # the Telegram chat id
    created_at: dt.datetime
    updated_at: dt.datetime = Field(index=True)  # UTC


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="chatthread.id", index=True)
    role: str  # user | model
    text: str = ""
    image_path: str | None = None  # under data_dir; a photo the person attached
    image_mime: str | None = None
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    # Things the AI offered to record: [{id, name, args, label, status: pending|done|dismissed|failed, result}]
    actions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: dt.datetime
