"""Reads a body-measurement CSV (smart-scale exports, spreadsheets) into per-day values.

Nothing here touches the database or logs the file: it turns bytes into a preview, and the router writes it.
"""
import csv
import datetime as dt
import io
import math
import re
from dataclasses import dataclass, field

from services import clock, profile as profile_svc
from services.i18n import msg

MAX_BYTES = 2 * 1024 * 1024
LB_TO_KG = 0.45359237
PREVIEW_ROWS = 200
SKIPPED_CAP = 50
DELIMITERS = ("\t", ";", ",")

DATE_ALIASES = {"date", "дата", "time", "время", "timestamp", "measured", "measuredat", "measuredon", "dateandtime", "datetime", "датаивремя", "датавремя"}
# normalized header -> (kind, factor to the stored unit)
KIND_ALIASES: dict[str, tuple[str, float]] = {}
for _kind, _names in {
    "weight": ("weight", "вес", "bodymass", "weightkg", "вескг", "weightbody", "bodyweight", "вестела"),
    "body_fat_pct": ("bodyfat", "fat", "жир", "процентжира", "bodyfatpercentage", "fatpercentage", "жирпроцент", "жирворганизме"),
    "muscle_kg": ("muscle", "musclemass", "мышцы", "мышечнаямасса", "skeletalmuscle", "musclekg", "мышцыкг"),
    "body_water_pct": ("water", "bodywater", "вода", "водаворганизме", "водапроцент"),
    "bone_kg": ("bone", "bonemass", "кости", "костнаямасса", "bonekg"),
    "visceral_fat": ("visceralfat", "висцеральныйжир", "висцеральныйжирindex", "visceral"),
    "bmr_kcal": ("bmr", "basalmetabolicrate", "основнойобмен", "bmrkcal", "основнойобменккал"),
    "skeletal_muscle_kg": ("skeletalmusclemass", "skeletalmusclekg", "скелетныемышцыкг", "скелетнаямышечнаямасса"),
    "skeletal_muscle_pct": ("skeletalmusclepercentage", "skeletalmusclepct", "скелетныемышцыпроцент"),
    "protein_pct": ("protein", "proteinpercentage", "proteinpct", "белок", "белокпроцент"),
    "body_age": ("bodyage", "metabolicage", "возрасттела", "метаболическийвозраст"),
    "hip": ("hip", "hips", "бедра", "окрбедер", "обьембедер"),
    "fat_mass_kg": ("fatmass", "fatmasskg", "жировая масса", "жироваямасса", "жироваямассакг"),
    "lean_mass_kg": ("leanmass", "leanbodymass", "fatfreemass", "тощаямасса", "тощаямассакг"),
    "active_cell_mass_kg": ("activecellmass", "bodycellmass", "активнаяклеточнаямасса", "активнаяклеточнаямассакг"),
    "active_cell_mass_pct": ("activecellmasspct", "доляактивнойклеточноймассы"),
    "total_body_water_kg": ("totalbodywater", "tbw", "общаяжидкость", "общаяжидкостькг"),
    "extracellular_water_kg": ("extracellularwater", "ecw", "внеклеточнаяжидкость", "внеклеточнаяжидкостькг"),
    "ecw_icw_ratio": ("ecwicw", "ecwicwratio", "extracellulartointracellular", "отношениевкжкж", "отношениевкжок"),
    "phase_angle": ("phaseangle", "фазовыйугол", "фазовыйуголград"),
    "specific_bmr": ("specificbmr", "удельныйосновнойобмен"),
    "waist": ("waist", "талия", "waistcm", "талиясм", "обьемталии"),
}.items():
    for _n in _names:
        KIND_ALIASES[_n] = (_kind, 1.0)
for _n in ("weightlb", "weightlbs", "lb", "lbs", "weightpounds", "weightpound"):
    KIND_ALIASES[_n] = ("weight", LB_TO_KG)


class ImportError_(Exception):
    """A whole-file problem; `status` and `key` pick the HTTP answer."""

    def __init__(self, status: int, key: str):
        super().__init__(key)
        self.status, self.key = status, key


PCT_KINDS = {"body_fat_pct", "body_water_pct"}
MASS_KINDS = {"weight", "muscle_kg", "bone_kg"}
_UNIT_PCT = re.compile(r"%")
_UNIT_MASS = re.compile(r"(?<![a-zа-яё])(?:kg|кг|lbs?|фунт\w*|pounds?)(?![a-zа-яё])", re.I)


def unit_contradicts(header: str, kind: str) -> bool:
    """True when the unit written in the raw header (%, kg, lb, кг) is not the unit this kind is stored in."""
    if kind in PCT_KINDS:
        return bool(_UNIT_MASS.search(header))
    if kind in MASS_KINDS:
        return bool(_UNIT_PCT.search(header))
    return False


def normalize_header(header: str) -> str:
    text = header.strip().lower().replace("ё", "е")
    return re.sub(r"[^\w]|_", "", text)


def decode(data: bytes) -> tuple[str, str]:
    for encoding, label in (("utf-8-sig", "utf-8"), ("cp1251", "cp1251")):
        try:
            return data.decode(encoding), label
        except UnicodeDecodeError:
            continue
    raise ImportError_(422, "http.import_undecodable")


def sniff_delimiter(text: str) -> str:
    header = next((line for line in text.splitlines() if line.strip()), "")
    best, best_count = ",", 1
    for delimiter in DELIMITERS:
        try:
            count = len(next(csv.reader([header], delimiter=delimiter)))
        except (csv.Error, StopIteration):
            continue
        if count > best_count:
            best, best_count = delimiter, count
    return best


_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ]+(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?)?\s*(Z|[+-]\d\d:?\d\d)?$")
_DMY = re.compile(r"^(\d{1,2})([./-])(\d{1,2})\2(\d{4})(?:[T ]+(\d{1,2}):(\d{2})(?::\d{2})?)?$")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")


@dataclass
class _Stamp:
    """A date as read from one cell: resolved (day set) or ambiguous (a, b, year) until the file's order is known."""
    day: dt.date | None
    minutes: int = 0
    ambiguous: tuple[int, int, int] | None = None


def _clock(h: str | None, m: str | None) -> int:
    return int(h) * 60 + int(m) if h is not None else 0


def _safe_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def _offset(token: str) -> dt.timezone:
    if token == "Z":
        return dt.timezone.utc
    sign = -1 if token[0] == "-" else 1
    digits = token[1:].replace(":", "")
    return dt.timezone(sign * dt.timedelta(hours=int(digits[:2]), minutes=int(digits[2:])))


def parse_stamp(text: str, zone: dt.tzinfo | None = None) -> _Stamp | None:
    """A cell as a date. A time with Z or an offset is an instant: it is moved into `zone` (the owner's) before the
    day is taken; one without is the day as written."""
    text = text.strip()
    if m := _ISO.match(text):
        day = _safe_date(int(m[1]), int(m[2]), int(m[3]))
        if day is None:
            return None
        if m[6] and m[4] is not None:
            local = dt.datetime(day.year, day.month, day.day, int(m[4]), int(m[5]), tzinfo=_offset(m[6])).astimezone(zone or clock.system_zone())
            return _Stamp(local.date(), local.hour * 60 + local.minute)
        return _Stamp(day, _clock(m[4], m[5]))
    if m := _DMY.match(text):
        a, sep, b, year = int(m[1]), m[2], int(m[3]), int(m[4])
        minutes = _clock(m[5], m[6])
        if sep == ".":
            day = _safe_date(year, b, a)
            return _Stamp(day, minutes) if day else None
        return _Stamp(None, minutes, (a, b, year))
    return None


def parse_time_only(text: str) -> int | None:
    m = _TIME.match(text.strip())
    return _clock(m[1], m[2]) if m and int(m[1]) < 24 and int(m[2]) < 60 else None


def parse_number(text: str) -> float | None:
    cleaned = re.sub(r"[\s ]", "", text).replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


@dataclass
class ImportResult:
    delimiter: str
    encoding: str
    columns: list[dict]
    day_first: bool
    values: dict[tuple[dt.date, str], float] = field(default_factory=dict)
    skipped: list[dict] = field(default_factory=list)
    skipped_total: int = 0
    warnings: list[str] = field(default_factory=list)

    def preview(self) -> tuple[list[dict], int]:
        days: dict[dt.date, dict[str, float]] = {}
        for (day, kind), value in sorted(self.values.items()):
            days.setdefault(day, {})[kind] = value
        rows = [{"date": d.isoformat(), "values": v} for d, v in days.items()]
        return rows[-PREVIEW_ROWS:], len(rows)


def parse_csv(data: bytes, lang: str, today: dt.date, zone: dt.tzinfo | None = None) -> ImportResult:
    text, encoding = decode(data)
    delimiter = sniff_delimiter(text)
    try:
        table = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in row)]
    except csv.Error as error:  # e.g. a field longer than the csv module's limit
        raise ImportError_(422, "http.import_undecodable") from error
    if not table:
        raise ImportError_(422, "http.import_empty")
    headers = table[0]
    date_cols: list[int] = []
    kind_cols: list[tuple[int, str, float]] = []
    columns = []
    warn_units: list[str] = []
    for i, header in enumerate(headers):
        key = normalize_header(header)
        if key in DATE_ALIASES:
            date_cols.append(i)
            mapped = "date"
        elif key in KIND_ALIASES:
            kind, factor = KIND_ALIASES[key]
            if unit_contradicts(header, kind):
                warn_units.append(header.strip())
                mapped = None
            else:
                kind_cols.append((i, kind, factor))
                mapped = kind
        else:
            mapped = None
        columns.append({"header": header.strip(), "mapped_to": mapped})
    if not date_cols:
        raise ImportError_(422, "http.import_no_date")
    if not kind_cols:
        raise ImportError_(422, "http.import_no_values")
    if len(table) < 2:
        raise ImportError_(422, "http.import_empty")

    result = ImportResult(delimiter=delimiter, encoding=encoding, columns=columns, day_first=True)
    for name in warn_units:
        result.warnings.append(msg(lang, "import.warn_unit_mismatch", name=name))
    unknown = [c["header"] for c in columns if c["mapped_to"] is None and c["header"] and c["header"] not in warn_units]
    if unknown:
        result.warnings.append(msg(lang, "import.warn_unknown_columns", names=", ".join(unknown)))
    if any(f != 1.0 for _, _, f in kind_cols):
        result.warnings.append(msg(lang, "import.warn_lb"))

    multiline = sum(1 for row in table for c in row if "\n" in c)
    if multiline:
        result.warnings.append(msg(lang, "import.warn_multiline", n=multiline))
    if delimiter == "," and any(re.fullmatch(r"\d+,\d+", row[i].strip()) for row in table[1:] for i, _, _ in kind_cols if i < len(row)):
        result.warnings.append(msg(lang, "import.warn_decimal_comma"))

    def cell(row: list[str], i: int) -> str:
        return row[i].strip() if i < len(row) else ""

    # Pass 1: read every date cell and decide the day/month order for the whole file.
    stamps: list[tuple[int, list[str], _Stamp | None, int | None, str]] = []
    for line, row in enumerate(table[1:], start=2):
        stamp, extra_minutes, raw = None, None, ""
        for i in date_cols:
            value = cell(row, i)
            if not value:
                continue
            raw = raw or value
            parsed = parse_stamp(value, zone)
            if parsed is not None and stamp is None:
                stamp = parsed
            elif (t := parse_time_only(value)) is not None and extra_minutes is None:
                extra_minutes = t
        stamps.append((line, row, stamp, extra_minutes, raw))
    firsts = [s.ambiguous[0] for _, _, s, _, _ in stamps if s and s.ambiguous]
    seconds = [s.ambiguous[1] for _, _, s, _, _ in stamps if s and s.ambiguous]
    if firsts:
        big_first, big_second = any(a > 12 for a in firsts), any(b > 12 for b in seconds)
        if big_second and not big_first:
            result.day_first = False
        elif big_first and big_second:
            result.warnings.append(msg(lang, "import.warn_mixed_order"))
        elif not big_first:
            result.warnings.append(msg(lang, "import.warn_day_first"))

    def skip(line: int, reason: str) -> None:
        result.skipped_total += 1
        if len(result.skipped) < SKIPPED_CAP:
            result.skipped.append({"line": line, "reason": reason})

    best: dict[tuple[dt.date, str], tuple[int, float]] = {}
    for line, row, stamp, extra, raw in stamps:
        if any(c.strip() for c in row[len(headers):]):
            skip(line, msg(lang, "import.skip_extra_cells", cells=len(row), columns=len(headers)))
            continue
        day, minutes = None, 0
        if stamp is not None:
            if stamp.ambiguous:
                a, b, year = stamp.ambiguous
                day = _safe_date(year, b, a) if result.day_first else _safe_date(year, a, b)
            else:
                day = stamp.day
            minutes = stamp.minutes or (extra or 0)
        if day is None:
            skip(line, msg(lang, "import.skip_bad_date", value=raw[:30]))
            continue
        if day > today:
            skip(line, msg(lang, "import.skip_future", date=day.isoformat()))
            continue
        taken, failed = set(), False
        for i, kind, factor in kind_cols:
            raw_value = cell(row, i)
            if not raw_value or kind in taken:
                continue
            number = parse_number(raw_value)
            label = msg(lang, f"import.kind_{kind}")
            if number is None:
                skip(line, msg(lang, "import.skip_bad_number", kind=label, value=raw_value[:30]))
                failed = True
                continue
            value = round(number * factor, 2)
            if not profile_svc.in_range(kind, value):
                lo, hi = profile_svc.VALUE_RANGE[kind]
                skip(line, msg(lang, "import.skip_range", kind=label, value=f"{value:g}", lo=f"{lo:g}", hi=f"{hi:g}"))
                failed = True
                continue
            taken.add(kind)
            key = (day, kind)
            if key not in best or minutes >= best[key][0]:
                best[key] = (minutes, value)
        if not taken and not failed:
            skip(line, msg(lang, "import.skip_no_values"))
    result.values = {key: value for key, (_, value) in best.items()}
    return result
