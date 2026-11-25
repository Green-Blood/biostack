"""Marker-name and unit normalization (English + Russian)."""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session, select

from db.models import MarkerAlias

_DIR = Path(__file__).parent


@dataclass(frozen=True)
class MarkerMatch:
    marker_key: str
    display_name: str


def _tokens(name: str) -> str:
    """Order-, case-, punctuation-insensitive signature of a marker name."""
    s = name.lower().replace("ё", "е")
    return " ".join(sorted(re.findall(r"[^\W_]+", s)))


@lru_cache(maxsize=1)
def _static_index() -> dict[str, MarkerMatch]:
    index: dict[str, MarkerMatch] = {}
    for entry in json.loads((_DIR / "marker_aliases.json").read_text(encoding="utf-8")):
        match = MarkerMatch(entry["marker_key"], entry["display_name"])
        for alias in [entry["display_name"], *entry["aliases"]]:
            index.setdefault(_tokens(alias), match)
    return index


@lru_cache(maxsize=1)
def _russian_names() -> dict[str, str]:
    entries = json.loads((_DIR / "marker_aliases.json").read_text(encoding="utf-8"))
    return {e["marker_key"]: e["display_name_ru"] for e in entries if e.get("display_name_ru")}


def marker_display_name(marker_key: str, stored_name: str, lang: str = "en") -> str:
    """The name to show: the Russian catalog name for Russian, else the name stored with the result."""
    return (_russian_names().get(marker_key) if lang == "ru" else None) or stored_name


def known_marker_names() -> list[str]:
    """Display names of every marker the alias map knows, for autocomplete."""
    return sorted({m.display_name for m in _static_index().values()}, key=str.lower)


def normalize_marker(raw_name: str, session: Session | None = None) -> MarkerMatch | None:
    sig = _tokens(raw_name or "")
    if not sig:
        return None
    if session is not None:
        for alias in session.exec(select(MarkerAlias)):
            if _tokens(alias.raw_name) == sig:
                return MarkerMatch(alias.marker_key, alias.display_name)
    return _static_index().get(sig)


@lru_cache(maxsize=1)
def _units() -> dict[str, str]:
    return json.loads((_DIR / "unit_aliases.json").read_text(encoding="utf-8"))


def canonical_unit(marker_key: str, unit: str) -> str:
    u = (unit or "").strip()
    return _units().get(u.lower().replace(" ", ""), u)


def units_compatible(a: str, b: str) -> bool:
    return canonical_unit("", a) == canonical_unit("", b)


MARKER_SYSTEMS = ("thyroid", "liver", "lipids", "blood_count", "minerals", "inflammation", "hormones", "vitamins",
                  "glucose", "coagulation", "kidney", "pancreas", "other")


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict]:
    entries = json.loads((_DIR / "marker_aliases.json").read_text(encoding="utf-8"))
    return {e["marker_key"]: e for e in entries}


def catalog_markers(lang: str = "en") -> list[dict]:
    """Every catalog marker as {marker_key, display_name, system}, named for `lang` and sorted by that name."""
    out = [{"marker_key": k, "display_name": marker_display_name(k, e["display_name"], lang),
            "system": e.get("system", "other")} for k, e in _catalog().items()]
    return sorted(out, key=lambda m: m["display_name"].lower())


def marker_system(marker_key: str) -> str:
    """The body system a catalog marker belongs to; anything unmapped is "other"."""
    return _catalog().get(marker_key, {}).get("system", "other")


def marker_retest_days(marker_key: str) -> int | None:
    """Suggested re-test interval in days (a rule of thumb, not medical advice); None for unmapped markers."""
    return _catalog().get(marker_key, {}).get("retest_days")
