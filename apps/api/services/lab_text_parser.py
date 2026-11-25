"""Read results straight from the text layer of a lab PDF, with no AI.

Conservative by design: a row is kept only when its value is followed by a reference range, a known-looking unit
or nothing at all. Anything it is unsure about is dropped, and sex- or age-specific ranges are left blank rather
than guessed. The owner still reviews every draft before it is saved.
"""
import datetime as dt
import io
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from sqlmodel import Session

from services.gemini_parser import ParsedLab
from services.lab_rows import LabRow, TierBand, resolve_row
from services.lab_table_parser import parse_reference
from services.markers import units_compatible
from services import clock
from services.app_settings import configured_zone
from services.profile import age_on, load_profile
from services.range_candidates import UNMODELLED, RangeCandidate, analyze, select_candidate

_NUMBER = r"[<>]?\d+(?:[.,]\d+)?"
_NUMBER_TOKEN = re.compile(rf"(?<![\w.,/-])({_NUMBER})(?![\w])")
_DATE = re.compile(r"Дата(?!\s*рождения)\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})", re.I)
_STAMPED_VALUE = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})\s+\d{{2}}:\d{{2}}:\d{{2}}\s+({_NUMBER})$")
_NORM_LINE = re.compile(r"^(?:норма|нормальное состояние)\s*:?\s*(?:от\s+)?(\d+(?:[.,]\d+)?)\s*(?:-|–|до)\s*(\d+(?:[.,]\d+)?)\s*(.*)$", re.I)
# tier words count only as the first words of the label: "Highly sensitive CRP" or "Prediabetes high risk" are not tiers
_TIER_WORDS = ((r"^потенциальная токсичность", "toxic"), (r"^дефицит", "deficient"), (r"^недостаточн", "insufficient"),
               (r"^токсичн", "toxic"), (r"^повышен", "high"), (r"^избыт", "high"), (r"^норм", "normal"),
               (r"^deficien", "deficient"), (r"^insufficien", "insufficient"), (r"^toxic\b", "toxic"),
               (r"^(?:high|elevated|excess)\b", "high"), (r"^normal\b", "normal"))
_TIER_LINE = re.compile(r"^(?P<label>[^:\d<>]*[A-Za-zА-Яа-яЁё][^:\d<>]*?)\s*:\s*(?P<body>.+)$")
_TIER_BODY = re.compile(r"^(?:от\s+)?(?P<lt>[<>])?\s*(?P<a>\d+(?:[.,]\d+)?)\s*(?:(?:-|–|до)\s*(?P<b_lt><)?\s*(?P<b>\d+(?:[.,]\d+)?))?\s*(?P<unit>[^\d]*)$")
_RESULTS_HEADER = re.compile(r"результат|result", re.I)
_NORM_HEADER = re.compile(r"норма|референс|reference|ref\.? ?range|ед\.? ?изм|unit", re.I)
_SEX_SPECIFIC = re.compile(r"(?:^|\s)[МЖ][.:]\s", re.I)
_LEADING_QUALIFIER = re.compile(r"^(?:[МЖ][.:]|муж|жен|взросл|дет[иь]|до\s+\d+\s*(?:лет|года)|старше|младше|от\s+\d+\s*(?:-|до)\s*\d+\s*(?:лет|года))", re.I)
_UNIT = re.compile(r"(?:%|(?:10[¹²³⁴⁵⁶⁷⁸⁹⁰^*]*\d*/[A-Za-zА-Яа-яЁё]+)|[A-Za-zµμА-Яа-яЁё][A-Za-zµμА-Яа-яЁё0-9¹²³⁹/.*^-]*(?:/[A-Za-zµμА-Яа-яЁё0-9¹²³⁹л]+)?)\s*$")
_NOISE = re.compile(r"женщин|мужчин|старше|младше|выше|ниже|токс\w*|токч\w*|анализ\s+(?:крови|мочи)$", re.I)  # age bands, interpretation fragments, section headings
_NOT_RESULTS = ("дата", "date", "patient", "phone", "ф.и.о", "телефон", "страница", "стр.", "page", "возраст", "адрес", "недостаточность",
                "дефицит", "норма", "оптимальн", "избыток", "риск", "референс")


def _num(token: str) -> float:
    return float(token.lstrip("<>").replace(",", "."))


def _tier_line(line: str) -> tuple[TierBand, str] | None:
    head = _TIER_LINE.match(line.strip())
    if head is None:
        return None
    label = head.group("label").strip()
    tier = next((name for pattern, name in _TIER_WORDS if re.search(pattern, label.lower())), None)
    body = _TIER_BODY.match(head.group("body").strip())
    if tier is None or body is None:
        return None
    first, second = _num(body.group("a")), (_num(body.group("b")) if body.group("b") else None)
    unit = body.group("unit").strip()
    if second is not None:
        return TierBand(tier=tier, min=first, max=second, label=label), unit
    if body.group("lt") == "<":
        return TierBand(tier=tier, max=first, label=label), unit
    if body.group("lt") == ">":
        return TierBand(tier=tier, min=first, label=label), unit
    return None  # a lone number is not a band


def parse_tier_line(line: str) -> TierBand | None:
    """A band from an interpretation line such as "недостаточность: 10 - < 29 ng/ml", else None."""
    found = _tier_line(line)
    return found[0] if found else None


def _starts_with_qualifier(line: str, found: list[RangeCandidate]) -> bool:
    """A line that opens with a qualifier ("Ж. 120-140", "старше 60 лет 10-21"), not one that merely contains one."""
    return bool(_LEADING_QUALIFIER.match(line))


def _join_wrapped(lines: list[str]) -> list[str]:
    """A name that opens a bracket and does not close it continues on the next line."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.count("(") > line.count(")") and index + 1 < len(lines):
            line = f"{line} {lines[index + 1]}"
            index += 1
        out.append(line)
        index += 1
    return out


class _Found(list):
    """Qualified ranges read from one line, and whether its qualifiers were unreadable."""
    undecidable = False


def _reference_and_unit(rest: str, candidates: list[RangeCandidate] | None = None) -> tuple[float | None, float | None, str | None, bool]:
    """(ref_min, ref_max, unit, understood) for the text that follows a value; qualified ranges go to `candidates`.
    A line whose qualifiers cannot be read unambiguously, or that names one we do not model (pregnancy, menopause,
    cycle phase), is understood but left blank, with no candidates."""
    rest = rest.strip()
    if not rest:
        return None, None, None, True
    found, undecidable = analyze(rest)
    if found and candidates is not None:
        candidates.extend(found)
    if (undecidable or UNMODELLED.search(rest)) and isinstance(candidates, _Found):
        candidates.undecidable = True
    if found or undecidable or UNMODELLED.search(rest) or _SEX_SPECIFIC.search(f" {rest}"):
        unit = _UNIT.search(rest)
        return None, None, unit.group(0).strip() if unit else None, True
    ref_min, ref_max = parse_reference(rest)
    unit_match = _UNIT.search(rest)
    unit = unit_match.group(0).strip() if unit_match else None
    if ref_min is None and ref_max is None:
        return None, None, None, False
    return ref_min, ref_max, unit, True


def _row_from_line(line: str, candidates: list[RangeCandidate] | None = None) -> LabRow | None:
    for match in _NUMBER_TOKEN.finditer(line):
        name = line[:match.start()].strip(" :;-")
        if sum(ch.isalpha() for ch in name) < 3 or ":" in name or "+" in name:
            continue
        if name.lower().startswith(_NOT_RESULTS) or _NOISE.search(name):
            return None
        ref_min, ref_max, unit, understood = _reference_and_unit(line[match.end():], candidates)
        if understood:
            return LabRow(name=name, value=_num(match.group(1)), unit=unit, ref_min=ref_min, ref_max=ref_max)
    return None


def _first_date(text: str) -> dt.date | None:
    match = _DATE.search(text)
    if match is None:
        return None
    raw = match.group(1)
    try:
        return dt.date.fromisoformat(raw) if "-" in raw else dt.datetime.strptime(raw, "%d.%m.%Y").date()
    except ValueError:
        return None


def extract_pdf_text(content: bytes) -> str:
    """The text layer of a PDF, or an empty string for a scan, an encrypted file or a damaged one."""
    try:
        return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(content)).pages)
    except (PyPdfError, ValueError, KeyError, OSError):
        return ""


def parse_lab_text(text: str, session: Session | None = None, on_date: dt.date | None = None) -> ParsedLab | None:
    """A draft lab report from extracted PDF text, or None when no result rows are recognised.
    `on_date` is the report's own date for choosing an age-specific range (default: the date printed in the text)."""
    if not (_RESULTS_HEADER.search(text or "") and _NORM_HEADER.search(text or "")):
        return None  # no results table: a clinical note or scan report, not a lab report
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    lines = _join_wrapped([line for line in lines if line])
    rows: list[LabRow] = []
    cands: dict[int, list[RangeCandidate]] = {}  # qualified ranges per row index
    poisoned: set[int] = set()  # rows whose printed qualifiers could not be read: never filled
    test_date = _first_date(text or "")
    for index, line in enumerate(lines):
        stamped = _STAMPED_VALUE.match(line)
        if stamped and index > 0 and not any(ch.isdigit() for ch in lines[index - 1]):
            rows.append(LabRow(name=lines[index - 1], value=_num(stamped.group(2))))
            test_date = dt.date.fromisoformat(stamped.group(1))  # the result's own date beats the header's
            continue
        found = _tier_line(line)
        if found is not None and rows:
            band, band_unit = found
            if not (band_unit and rows[-1].unit and not units_compatible(band_unit, rows[-1].unit)):  # another unit: not this row's band
                rows[-1] = rows[-1].model_copy(update={"tiers": [*rows[-1].tiers, band]})
        norm = _NORM_LINE.match(line)
        if norm and rows and rows[-1].ref_min is None and rows[-1].ref_max is None:
            unit = _UNIT.search(norm.group(3))
            update = {"ref_min": _num(norm.group(1)), "ref_max": _num(norm.group(2))}
            if rows[-1].unit is None and unit:
                update["unit"] = unit.group(0).strip()
            rows[-1] = rows[-1].model_copy(update=update)
            continue
        if rows and rows[-1].ref_min is None and rows[-1].ref_max is None:
            more, undecidable = analyze(line)
            if (more or undecidable) and _starts_with_qualifier(line, more):
                if undecidable:
                    poisoned.add(len(rows) - 1)
                cands.setdefault(len(rows) - 1, []).extend(more)  # a qualified range wrapped onto its own line
                continue
        here = _Found()
        row = _row_from_line(line, here)
        if row is not None:
            rows.append(row)
            if here:
                cands[len(rows) - 1] = here
            if here.undecidable:
                poisoned.add(len(rows) - 1)
    if not rows:
        return None
    # a lone "normal" band only repeats the reference range, so it is not worth a tier
    rows = [r.model_copy(update={"tiers": []}) if all(t.tier == "normal" for t in r.tiers) else r for r in rows]
    facts = load_profile(session) if session is not None else None
    age = facts.age if facts else None
    if facts is not None and facts.birth_date is not None:  # the age at the time of the report, not today
        age = age_on(facts.birth_date, on_date or test_date or clock.today(configured_zone(session)))
    for index, found in cands.items():
        if index in poisoned:
            continue
        if rows[index].ref_min is None and rows[index].ref_max is None:
            chosen, needs = select_candidate(found, facts.sex if facts else None, age)
            update: dict = {"needs_profile": needs}
            if chosen is not None:
                update.update(ref_min=chosen[0], ref_max=chosen[1])
            rows[index] = rows[index].model_copy(update=update)
    return ParsedLab(test_date=test_date, lab_name="", rows=[resolve_row(row, session) for row in rows])
