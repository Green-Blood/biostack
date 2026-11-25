"""The owner's profile (birth date, sex, height), body measurements, BMI and the waist-to-height ratio.

BMI uses the WHO adult cut-offs and is shown for adults only; every number comes from what the owner entered.
"""
import dataclasses
import datetime as dt

from sqlmodel import Session, select

from db.models import BodyMeasurement, Profile
from services import clock
from services.app_settings import configured_zone

SEXES = ("female", "male")
KINDS = ("weight", "waist", "body_fat_pct", "muscle_kg", "body_water_pct", "bone_kg", "visceral_fat", "bmr_kcal",
         "skeletal_muscle_kg", "skeletal_muscle_pct", "protein_pct", "body_age",
         "hip", "fat_mass_kg", "lean_mass_kg", "active_cell_mass_kg", "active_cell_mass_pct", "total_body_water_kg", "extracellular_water_kg", "ecw_icw_ratio", "phase_angle", "specific_bmr")
MIN_BIRTH_YEAR = 1900
HEIGHT_RANGE = (50.0, 260.0)
VALUE_RANGE = {
    "weight": (20.0, 400.0), "waist": (30.0, 250.0), "body_fat_pct": (2.0, 70.0), "muscle_kg": (5.0, 120.0),
    "body_water_pct": (20.0, 80.0), "bone_kg": (0.5, 10.0), "visceral_fat": (1.0, 60.0), "bmr_kcal": (500.0, 5000.0),
    "skeletal_muscle_kg": (3.0, 80.0), "skeletal_muscle_pct": (5.0, 70.0), "protein_pct": (3.0, 40.0), "body_age": (5.0, 120.0),
    "hip": (40.0, 250.0),
    "fat_mass_kg": (1.0, 200.0),
    "lean_mass_kg": (10.0, 200.0),
    "active_cell_mass_kg": (5.0, 120.0),
    "active_cell_mass_pct": (20.0, 90.0),
    "total_body_water_kg": (10.0, 120.0),
    "extracellular_water_kg": (3.0, 60.0),
    "ecw_icw_ratio": (0.1, 3.0),
    "phase_angle": (1.0, 15.0),
    "specific_bmr": (300.0, 2000.0),
}
ADULT_AGE = 18
BMI_BANDS = (("underweight", None, 18.5), ("normal", 18.5, 25.0), ("overweight", 25.0, 30.0), ("obese", 30.0, None))


@dataclasses.dataclass(frozen=True)
class ProfileFacts:
    sex: str | None = None
    age: int | None = None
    birth_date: dt.date | None = None
    height_cm: float | None = None


def age_on(birth_date: dt.date | None, today: dt.date) -> int | None:
    if birth_date is None:
        return None
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def get_profile(session: Session) -> Profile:
    return session.get(Profile, 1) or Profile(id=1)


def load_profile(session: Session) -> ProfileFacts:
    p = get_profile(session)
    today = clock.today(configured_zone(session))
    return ProfileFacts(sex=p.sex, age=age_on(p.birth_date, today), birth_date=p.birth_date, height_cm=p.height_cm)


def save_profile(session: Session, changes: dict) -> Profile:
    p = session.get(Profile, 1) or Profile(id=1)
    for field, value in changes.items():
        setattr(p, field, value)
    p.updated_at = dt.datetime.now(dt.timezone.utc)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def bmi_category(bmi: float) -> str:
    """WHO adult cut-offs; each interval is closed below and open above. Callers pass the value as displayed (one
    decimal), so the category never disagrees with the number the owner reads."""
    if bmi < 18.5:
        return "underweight"
    if bmi < 25:
        return "normal"
    if bmi < 30:
        return "overweight"
    if bmi < 35:
        return "obese_1"
    if bmi < 40:
        return "obese_2"
    return "obese_3"


def bmi_value(weight_kg: float, height_cm: float) -> float:
    return weight_kg / (height_cm / 100) ** 2


def latest_measurement(session: Session, kind: str) -> BodyMeasurement | None:
    return session.exec(select(BodyMeasurement).where(BodyMeasurement.kind == kind).order_by(BodyMeasurement.measured_on.desc())).first()


def profile_payload(session: Session) -> dict:
    facts = load_profile(session)
    weight, waist = latest_measurement(session, "weight"), latest_measurement(session, "waist")
    bmi, status = None, "ok"
    if facts.birth_date is None:
        status = "needs_birth_date"
    elif facts.age < ADULT_AGE:
        status = "adult_only"
    elif facts.height_cm is None:
        status = "needs_height"
    elif weight is None:
        status = "needs_weight"
    else:
        shown = round(bmi_value(weight.value, facts.height_cm), 1)
        bmi = {"value": shown, "category": bmi_category(shown), "date": weight.measured_on.isoformat()}
    return {
        "birth_date": facts.birth_date.isoformat() if facts.birth_date else None,
        "age_years": facts.age,
        "sex": facts.sex,
        "height_cm": facts.height_cm,
        "latest_weight": {"date": weight.measured_on.isoformat(), "kg": weight.value} if weight else None,
        "latest_waist": {"date": waist.measured_on.isoformat(), "cm": waist.value} if waist else None,
        "bmi": bmi,
        "bmi_status": status,
        "whtr": round(waist.value / facts.height_cm, 2) if waist and facts.height_cm else None,
    }


def bmi_history(session: Session) -> dict:
    """BMI over time with today's height, for adults only: `points` is empty unless bmi_status is "ok"."""
    height = get_profile(session).height_cm
    status = profile_payload(session)["bmi_status"]
    points = []
    if height and status == "ok":
        for w in session.exec(select(BodyMeasurement).where(BodyMeasurement.kind == "weight").order_by(BodyMeasurement.measured_on)).all():
            shown = round(bmi_value(w.value, height), 1)
            points.append({"date": w.measured_on.isoformat(), "weight_kg": w.value, "bmi": shown, "category": bmi_category(shown)})
    return {"height_cm": height, "points": points, "bmi_status": status,
            "bands": [{"key": k, "min": lo, "max": hi} for k, lo, hi in BMI_BANDS]}


def in_range(kind: str, value: float) -> bool:
    lo, hi = VALUE_RANGE[kind]
    return lo <= value <= hi


def upsert_measurements(session: Session, values: dict[tuple[dt.date, str], float], source: str) -> int:
    """Writes one value per (day, kind); an existing row is replaced. Returns how many existing rows were replaced."""
    replaced = 0
    for (day, kind), value in values.items():
        row = session.exec(select(BodyMeasurement).where(BodyMeasurement.measured_on == day, BodyMeasurement.kind == kind)).first()
        if row is None:
            row = BodyMeasurement(measured_on=day, kind=kind, value=value)
        else:
            replaced += 1
        row.value, row.source = value, source
        session.add(row)
    session.commit()
    return replaced


CHUNK = 500  # bound parameters per query


def _existing(session: Session, keys: set[tuple[dt.date, str]], manual_only: bool = False,
              not_source: str | None = None) -> set[tuple[dt.date, str]]:
    days = sorted({d for d, _ in keys})
    found: set[tuple[dt.date, str]] = set()
    for start in range(0, len(days), CHUNK):
        query = select(BodyMeasurement).where(BodyMeasurement.measured_on.in_(days[start:start + CHUNK]))
        if manual_only:
            query = query.where(BodyMeasurement.source == "manual")
        if not_source is not None:
            query = query.where(BodyMeasurement.source != not_source)
        found |= {(r.measured_on, r.kind) for r in session.exec(query).all()}
    return found & keys


def existing_keys(session: Session, keys: set[tuple[dt.date, str]]) -> set[tuple[dt.date, str]]:
    """The (day, kind) pairs among `keys` that already hold a value."""
    return _existing(session, keys)


def manual_keys(session: Session, keys: set[tuple[dt.date, str]]) -> set[tuple[dt.date, str]]:
    """The (day, kind) pairs among `keys` that the owner entered by hand."""
    return _existing(session, keys, manual_only=True)


def keys_owned_by_others(session: Session, keys: set[tuple[dt.date, str]], source: str) -> set[tuple[dt.date, str]]:
    """The (day, kind) pairs among `keys` that already hold a value written by anything other than `source`."""
    return _existing(session, keys, not_source=source)


def existing_days(session: Session, keys: set[tuple[dt.date, str]]) -> int:
    return len(existing_keys(session, keys))


def body_summary(session: Session) -> dict:
    """Latest value per kind and the value from the closest earlier day, for kinds that exist."""
    latest: dict[str, dict] = {}
    previous: dict[str, dict] = {}
    rows = session.exec(select(BodyMeasurement).order_by(BodyMeasurement.measured_on.desc())).all()
    for r in rows:
        point = {"date": r.measured_on.isoformat(), "value": r.value}
        if r.kind not in latest:
            latest[r.kind] = point
        elif r.kind not in previous:
            previous[r.kind] = point
    return {"latest": latest, "previous": previous}
