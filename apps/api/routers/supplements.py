import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, Field, field_validator
from sqlmodel import Session, select

from db.database import get_session
from db.models import SupplementLog
from services import app_settings
from services.app_settings import Category, Preset
from services.half_life_engine import FALLBACK_HALF_LIFE_HOURS, Dose, DEFAULT_HALF_LIFE_HOURS, as_utc, at_bedtime
from services.i18n import Lang, get_lang, msg

router = APIRouter(prefix="/supplements", tags=["supplements"])


class QuickLog(BaseModel):
    item_name: str
    dosage: float | None = Field(default=None, gt=0)
    unit: str = ""
    category: Category = "supplement"
    timestamp: AwareDatetime | None = None
    half_life_hours: float | None = Field(default=None, gt=0)

    @field_validator("item_name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the item a name.")
        return value.strip()


class SupplementOut(BaseModel):
    id: int
    timestamp: dt.datetime
    item_name: str
    dosage: float | None
    unit: str
    category: str
    half_life_hours: float | None

    @classmethod
    def of(cls, log: SupplementLog) -> "SupplementOut":
        return cls(id=log.id, timestamp=as_utc(log.timestamp), item_name=log.item_name, dosage=log.dosage,
                   unit=log.unit, category=log.category, half_life_hours=log.half_life_hours)


class BedtimeItem(BaseModel):
    item_name: str
    unit: str
    remaining: float


class BedtimeReadout(BaseModel):
    bedtime: str
    items: list[BedtimeItem]


@router.post("/quick", status_code=201)
def quick_log(body: QuickLog, session: Session = Depends(get_session)) -> SupplementOut:
    half_life = body.half_life_hours or app_settings.half_life_for(body.item_name, app_settings.load_presets(session))
    log = SupplementLog(
        timestamp=body.timestamp or dt.datetime.now(dt.timezone.utc), item_name=body.item_name, dosage=body.dosage,
        unit=body.unit, category=body.category, half_life_hours=half_life,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return SupplementOut.of(log)


@router.get("")
def list_logs(days: int = Query(7, ge=1), session: Session = Depends(get_session)) -> list[SupplementOut]:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    logs = session.exec(select(SupplementLog).where(SupplementLog.timestamp >= since).order_by(SupplementLog.timestamp.desc()))
    return [SupplementOut.of(log) for log in logs]


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: int, session: Session = Depends(get_session), lang: Lang = Depends(get_lang)) -> Response:
    log = session.get(SupplementLog, log_id)
    if log is None:
        raise HTTPException(404, msg(lang, "http.supplement_log_not_found"))
    session.delete(log)
    session.commit()
    return Response(status_code=204)


@router.get("/presets")
def read_presets(session: Session = Depends(get_session)) -> list[Preset]:
    return app_settings.load_presets(session)


@router.put("/presets")
def replace_presets(presets: list[Preset], session: Session = Depends(get_session)) -> list[Preset]:
    return app_settings.save_presets(session, presets)


@router.get("/bedtime")
def bedtime_readout(session: Session = Depends(get_session)) -> BedtimeReadout:
    """How much of each stimulant logged in the last 48 hours is still in the body at tonight's bedtime."""
    bedtime = app_settings.load_settings(session).bedtime
    zone = app_settings.configured_zone(session)
    today = dt.datetime.now(zone).date()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
    logs = session.exec(select(SupplementLog).where(SupplementLog.category == "stimulant", SupplementLog.timestamp >= since)).all()
    by_item: dict[str, list[SupplementLog]] = {}
    for log in logs:
        by_item.setdefault(log.item_name, []).append(log)
    items = []
    for name, entries in by_item.items():
        default = DEFAULT_HALF_LIFE_HOURS.get(name.lower(), FALLBACK_HALF_LIFE_HOURS)
        doses = [Dose(e.timestamp, e.dosage or 0, e.half_life_hours) for e in entries]
        items.append(BedtimeItem(item_name=name, unit=entries[0].unit, remaining=at_bedtime(doses, today, bedtime, zone, default)))
    return BedtimeReadout(bedtime=bedtime, items=items)
