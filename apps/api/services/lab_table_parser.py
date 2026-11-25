"""Parse lab result tables found in Notion page bodies (markdown) into raw rows."""
import re
from dataclasses import dataclass

_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_RESULT_RE = re.compile(rf"^\s*([<>]=?|≤|≥)?\s*({_NUM})\s*(.*)$")
_RANGE_RE = re.compile(rf"({_NUM})\s*[-–—]\s*({_NUM})")
_UPPER_RE = re.compile(rf"^\s*(?:[<≤]=?|up\s+to|до)\s*({_NUM})", re.I)
_LOWER_RE = re.compile(rf"^\s*(?:[>≥]=?|от|>=)\s*({_NUM})", re.I)


@dataclass
class ParsedResult:
    value: float | None
    unit: str | None
    result_text: str | None
    comparator: str | None


@dataclass
class RawLabRow:
    name: str
    result: str
    reference: str
    interpretation: str
    unit: str = ""


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_result(text: str) -> ParsedResult:
    text = (text or "").strip()
    if not text:
        return ParsedResult(None, None, None, None)
    m = _RESULT_RE.match(text)
    if not m or re.match(rf"^[-–—]\s*{_NUM}", m.group(3)):  # "25–30" is a range, not 25 + unit
        return ParsedResult(None, None, text, None)
    comp, num, rest = m.groups()
    return ParsedResult(_num(num), rest.strip() or None, None, comp)


def parse_reference(text: str) -> tuple[float | None, float | None]:
    text = (text or "").replace("\\", "").strip()
    if not text:
        return (None, None)
    m = _RANGE_RE.search(text)
    if m:
        return (_num(m.group(1)), _num(m.group(2)))
    m = _UPPER_RE.match(text)
    if m:
        return (None, _num(m.group(1)))
    m = _LOWER_RE.match(text)
    if m:
        return (_num(m.group(1)), None)
    return (None, None)


_HEADERS = {
    "name": ("test", "parameter", "analysis", "marker", "name", "параметр", "показатель", "исследование", "анализ"),
    "result": ("result", "value", "результат", "значение"),
    "reference": ("reference", "range", "norm", "референс", "норма"),
    "unit": ("unit", "ед. изм", "единиц", "ед.изм"),
    "interpretation": ("interpretation", "comment", "заключение", "комментарий", "интерпретация"),
}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _column_map(header: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, cell in enumerate(header):
        low = cell.lower()
        for key, words in _HEADERS.items():
            if key not in found and any(w in low for w in words):
                found[key] = idx
                break
    return found


def parse_markdown_lab_table(md: str) -> list[RawLabRow]:
    lines = (md or "").splitlines()
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|?\s*$", lines[i + 1]):
            cols = _column_map(_cells(lines[i]))
            if "name" in cols and "result" in cols:
                rows = []
                j = i + 2
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    cells = _cells(lines[j])
                    get = lambda k: cells[cols[k]] if k in cols and cols[k] < len(cells) else ""
                    if get("name"):
                        rows.append(RawLabRow(get("name"), get("result"), get("reference"),
                                              get("interpretation"), get("unit")))
                    j += 1
                return rows
        i += 1
    return []
