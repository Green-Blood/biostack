"""The owner's few preferences, stored as JSON documents in the AppSetting table."""
import datetime as dt
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlmodel import Session

from db.models import AppSetting
from services.clock import local_zone
from services.half_life_engine import DEFAULT_HALF_LIFE_HOURS

CLOCK_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
Category = Literal["stimulant", "supplement", "medication"]


class UserSettings(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    bedtime: str = "23:00"
    timezone: str = ""
    ai_briefing: bool = False

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value) if value else None
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a time zone name such as Europe/Berlin, or leave it empty to follow this computer.") from exc
        return value

    @field_validator("bedtime")
    @classmethod
    def _clock_time(cls, value: str) -> str:
        if not CLOCK_TIME.match(value):
            raise ValueError("Bedtime must be written as HH:MM, for example 23:00.")
        return value

    @model_validator(mode="after")
    def _both_coordinates_or_neither(self) -> "UserSettings":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Enter both latitude and longitude, or leave both empty.")
        return self


class Preset(BaseModel):
    item_name: str = Field(min_length=1)
    dosage: float | None = Field(default=None, gt=0)
    unit: str = ""
    category: Category = "supplement"
    half_life_hours: float | None = Field(default=None, gt=0)

    @field_validator("item_name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the item a name.")
        return value.strip()


DEFAULT_PRESETS = [
    Preset(item_name="Caffeine", dosage=200, unit="mg", category="stimulant", half_life_hours=DEFAULT_HALF_LIFE_HOURS["caffeine"]),
    Preset(item_name="L-theanine", dosage=200, unit="mg", category="supplement", half_life_hours=DEFAULT_HALF_LIFE_HOURS["l-theanine"]),
    Preset(item_name="Magnesium", dosage=400, unit="mg", category="supplement"),
    Preset(item_name="Melatonin", dosage=1, unit="mg", category="supplement", half_life_hours=DEFAULT_HALF_LIFE_HOURS["melatonin"]),
]


def _read(session: Session, key: str) -> dict | list | None:
    row = session.get(AppSetting, key)
    return row.value if row else None


def _write(session: Session, key: str, value: dict | list) -> None:
    session.merge(AppSetting(key=key, value=value))
    session.commit()


def load_settings(session: Session) -> UserSettings:
    stored = _read(session, "profile")
    return UserSettings.model_validate(stored) if stored else UserSettings()


def configured_zone(session: Session) -> dt.tzinfo:
    return local_zone(load_settings(session).timezone)


def save_settings(session: Session, settings: UserSettings) -> UserSettings:
    _write(session, "profile", settings.model_dump())
    return settings


def load_presets(session: Session) -> list[Preset]:
    stored = _read(session, "presets")
    return [Preset.model_validate(item) for item in stored] if stored is not None else list(DEFAULT_PRESETS)


def save_presets(session: Session, presets: list[Preset]) -> list[Preset]:
    _write(session, "presets", [preset.model_dump() for preset in presets])
    return presets


def half_life_for(item_name: str, presets: list[Preset]) -> float | None:
    """The owner's preset wins over the built-in table."""
    name = item_name.strip().lower()
    for preset in presets:
        if preset.item_name.lower() == name:
            return preset.half_life_hours
    return DEFAULT_HALF_LIFE_HOURS.get(name)
