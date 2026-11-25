"""Lab result rows: validation of reviewed input and resolution to stored marker identity."""
import re
from typing import Literal, Self

from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Session

from services.markers import canonical_unit, normalize_marker


def is_out_of_range(value: float | None, ref_min: float | None, ref_max: float | None) -> bool:
    if value is None:
        return False
    return (ref_min is not None and value < ref_min) or (ref_max is not None and value > ref_max)


def slug(name: str) -> str:
    return re.sub(r"\W+", "_", name.lower()).strip("_")


def marker_identity(raw_name: str, session: Session | None = None) -> tuple[str, str, bool]:
    """(marker_key, display_name, mapped) for a name as printed on a lab report."""
    match = normalize_marker(raw_name, session)
    if match is None:
        return f"unmapped:{slug(raw_name)}", raw_name, False
    return match.marker_key, match.display_name, True


class TierBand(BaseModel):
    """A band the lab printed under a result: tier name, bounds in the row's unit, the lab's own wording."""
    tier: str
    min: float | None = None
    max: float | None = None
    label: str = ""


class LabRow(BaseModel):
    name: str
    value: float | None = None
    unit: str | None = None
    ref_min: float | None = None
    ref_max: float | None = None
    result_text: str | None = None
    tiers: list[TierBand] = []
    needs_profile: Literal["sex", "age", "both"] | None = None  # the range is blank only because the profile lacks this


class ReviewedRow(LabRow):
    """A row the owner has reviewed and wants stored."""

    @field_validator("name")
    @classmethod
    def _name_required(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Every result needs a marker name")
        return name

    @field_validator("result_text")
    @classmethod
    def _blank_text_is_none(cls, text: str | None) -> str | None:
        return (text or "").strip() or None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.value is None and self.result_text is None:
            raise ValueError(f"{self.name}: enter a value or a text result")
        if self.ref_min is not None and self.ref_max is not None and self.ref_min > self.ref_max:
            raise ValueError(f"{self.name}: the reference minimum is above the maximum")
        return self


class DraftRow(LabRow):
    unit: str = ""
    marker_key: str
    display_name: str
    mapped: bool
    is_out_of_range: bool


def resolve_row(row: LabRow, session: Session | None = None) -> DraftRow:
    key, display, mapped = marker_identity(row.name, session)
    return DraftRow(
        name=row.name.strip(), value=row.value, unit=canonical_unit(key, row.unit or ""),
        ref_min=row.ref_min, ref_max=row.ref_max, result_text=(row.result_text or "").strip() or None,
        tiers=row.tiers, needs_profile=row.needs_profile, marker_key=key, display_name=display, mapped=mapped,
        is_out_of_range=is_out_of_range(row.value, row.ref_min, row.ref_max),
    )
