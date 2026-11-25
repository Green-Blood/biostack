"""Rule-based extraction of organ measurements from ultrasound report text (EN and RU).

The text is cut into lines (and at inline organ headers like "(normal)Prostate:"), lines into sentences, and sentences
into clauses. A line that starts with an organ name sets the current organ; side words (right/left/правая/левая) set the
current side for the rest of the sentence. Each clause is matched against a fixed list of patterns; printed units are
converted to the catalog unit of the param. Only params known to the catalog are emitted; the first value printed for an
(organ, param, side) wins."""
import math
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from services.gemini_client import GeminiClient
from services.gemini_parser import ParseError
from services.organs import ORGANS, SIDES, get_param, organs_in


@dataclass(frozen=True)
class Measurement:
    organ_key: str
    param_key: str
    side: str
    value: float | None
    value_text: str | None
    unit: str


@dataclass
class Extraction:
    organs: list[str] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)


_NUM = r"\d+(?:[.,]\d+)?"
_LIN = r"(mm|мм|cm(?![³3²2])|см(?![³3²2]))"
_VOL = r"(cm³|cm3|см³|см3|ml|мл)"
_SEP = r"\s*[×xх*]\s*"
_DIMS = re.compile(rf"(?<![\d.,])({_NUM})({_SEP}{_NUM}){{1,2}}\s*{_LIN}")
_LIN_VALUE = re.compile(rf"(?<![\d.,])({_NUM})\s*{_LIN}")
_VOL_VALUE = re.compile(rf"(?<![\d.,])({_NUM})\s*{_VOL}")

_ORGAN_WORD = "(?:" + "|".join(re.escape(a) for o in ORGANS.values() for a in o.aliases) + r")\w*"
_SIDE_WORD = r"(?:right|left|правая|правой|левая|левой)"
_HEADER = re.compile(rf"^(?:{_SIDE_WORD}\s+)?{_ORGAN_WORD}(?:\s+\w+){{0,2}}?\s*(?:[:—–-]|$)")
_INLINE_HEADER = re.compile(rf"(?<!\w)(?:{_SIDE_WORD}\s+)?{_ORGAN_WORD}(?:\s+\w+){{0,2}}?\s*:")

_BULLETS = "•◦-–—*· \t"
_PAREN = re.compile(r"\([^()]*\)")
_RANGE = re.compile(rf"{_NUM}\s*[–-]\s*{_NUM}")
_SIDE = re.compile(r"\b(right|left|правая|правой|правую|левая|левой|левую|справа|слева|total|общий|общая|общем|суммарный)\b")
_SIDE_OF = {"right": "right", "правая": "right", "правой": "right", "правую": "right", "справа": "right",
            "left": "left", "левая": "left", "левой": "left", "левую": "left", "слева": "left"}

_TIRADS = re.compile(r"ti-?rads\s*:?\s*(\d)")
_NODULE = re.compile(r"nodul\w*|узел\w*|узл\w*")
# A nodule count is read only from a printed digit count: "2 nodules", "2 узла", "nodules: 2", "узлов: 2".
_NOT_DIM = r"(?![\d.,]|\s*[×xх*]\s*\d|\s*(?:mm|мм|cm|см)(?!\w))"
# a score word before the digit makes it a grade, not a count ("Bethesda 4 nodule", "TI-RADS 4 nodule")
_SCORE_BEFORE = r"(?<!bethesda )(?<!category )(?<!categ )(?<!class )(?<!type )(?<!grade )(?<!rads )" \
                r"(?<!категория )(?<!класс )(?<!тип )"
_NODULE_COUNT = re.compile(
    rf"{_SCORE_BEFORE}(?<![\d.,×xх*\w])(\d+){_NOT_DIM}\s+(?:[^\W\d_]+\s+)?(nodules?|узел|узла|узлов)\b"
    rf"|(?:nodules|узл\w*)\s*[:—-]\s*(\d+){_NOT_DIM}")


def _count_agrees(n: int, noun: str) -> bool:
    """The noun's number must fit the count ("4 nodule" and "4 узел" are grades or labels, not counts)."""
    if noun.startswith("nodul"):
        return (n == 1) == (noun == "nodule")
    ru = "узел" if n % 10 == 1 and n % 100 != 11 else "узла" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "узлов"
    return noun == ru
# Words naming a finding inside an organ: the dimensions printed with one are the finding's size, not the organ's.
_LESION = re.compile(r"\b(?:cyst|stone|calcul|concre|polyp|hemangiom|haemangiom|mass|lymph|lesion|focus|focal|"
                     r"кист|конкремент|камн|камен|полип|гемангиом|образовани|лимфоузл|лимфатическ|очаг)")
_WALL = re.compile(r"wall|стенк")
_RESIDUAL = re.compile(r"residual|остаточн")
_ISTHMUS = re.compile(rf"(?:isthmus|перешеек|перешейк\w*)\D{{0,12}}?({_NUM})\s*{_LIN}")
_PARENCHYMA = re.compile(rf"(?:parenchyma|паренхим\w*)\D{{0,20}}?({_NUM})\s*{_LIN}")
_PANCREAS_PART = re.compile(rf"(head|головк\w*|body|тело|tail|хвост\w*)\s*[:—-]?\s*({_NUM})\s*{_LIN}")
_PART_PARAM = {"head": "head_cm", "голов": "head_cm", "body": "body_cm", "тело": "body_cm",
               "tail": "tail_cm", "хвост": "tail_cm"}
# Clauses about vessels/ducts are never an organ size.
_NOT_ORGAN_SIZE = re.compile(r"vein|duct|artery|aorta|portal|cbd|ureter|вен|проток|артер|аорт|воротн|мочеточ")
# Organs whose single printed length is their size — only when the clause has no other noun (positive allow-list):
# besides the number it may hold only organ words, side words, lobe words and explicit size words.
_SINGLE_SIZE = {"liver": "lobe_size_cm", "spleen": "length_cm", "kidneys": "length_cm"}
_SIZE_CLAUSE_WORD = re.compile(
    rf"^(?:{_ORGAN_WORD}|{_SIDE_WORD}|правую|левую|lobe|доля|доли|size|sizes|length|dimensions?|long|"
    r"размер\w*|длин\w*|is|of|the|approx\w*|about|около)$")

_QUALITIES = {
    "echogenicity": r"echogenicity|эхогенност\w*",
    "vascularity": r"vascularity|vascularization|васкуляризаци\w*|кровоток\w*",
    "echotexture": r"echotexture|echostructure|эхоструктур\w*",
}
_QUALIFIER = (r"increased|decreased|reduced|normal|elevated|enhanced|preserved|moderate|low|high|"
              r"homogeneous|heterogeneous|inhomogeneous|coarse|"
              r"повышен\w*|снижен\w*|понижен\w*|нормальн\w*|обычн\w*|сохранен\w*|средн\w*|усилен\w*|"
              r"умерен\w*|однородн\w*|неоднородн\w*")
_QUALITY_AFTER = {k: re.compile(rf"(?:{w})\s*[:—-]?\s*(?:is\s+)?(?:\w+\s+){{0,2}}?({_QUALIFIER})\b")
                  for k, w in _QUALITIES.items()}
_QUALITY_BEFORE = {k: re.compile(rf"\b({_QUALIFIER})\s+(?:{w})") for k, w in _QUALITIES.items()}


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _to_unit(value: float, printed: str, target: str) -> float | None:
    printed = {"мм": "mm", "см": "cm"}.get(printed, printed)
    if target in ("cm³", "ml"):
        return value if printed in ("cm³", "cm3", "см³", "см3", "ml", "мл") else None
    if target == printed:
        return value
    if (printed, target) == ("cm", "mm"):
        return round(value * 10, 4)
    if (printed, target) == ("mm", "cm"):
        return round(value / 10, 4)
    return None


def _blank(text: str, m: re.Match) -> str:
    """Mark a matched span as used so later patterns do not read it again."""
    return text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]


def _clean(line: str) -> str:
    """Drop text that must never yield a value: '(normal …)' notes, parenthesised ranges, bare a–b ranges."""
    def paren(m: re.Match) -> str:
        inner = m.group(0)
        # a dropped note still ends the clause, so a side word after it cannot claim the values before it
        return " ; " if ("normal" in inner or "норм" in inner or _RANGE.search(inner)) else inner
    return _RANGE.sub(" ", _PAREN.sub(paren, line))


def _lines(text: str) -> list[str]:
    out = []
    for raw in text.lower().replace("ё", "е").splitlines():
        line = raw.strip(_BULLETS)
        cuts = [m.start() for m in _INLINE_HEADER.finditer(line) if m.start() > 0]
        for a, b in zip([0, *cuts], [*cuts, len(line)]):
            piece = line[a:b].strip(_BULLETS)
            if piece:
                out.append(piece)
    return out


class _Collector:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], Measurement] = {}
        self.nodules: dict[str, list[float]] = {}  # largest side of every printed nodule dimension group
        self.nodule_counts: dict[str, int] = {}  # first printed count per organ
        self.tirads: dict[str, int] = {}  # highest printed score per organ

    def add(self, organ: str | None, param_key: str, side: str, value: float | str | None, printed: str = "") -> None:
        param = get_param(organ, param_key) if organ else None
        if param is None or value is None:
            return
        side = side if param.sides else ""
        if param.sides and side not in ("left", "right"):
            return
        if param.kind == "text":
            m = Measurement(organ, param_key, side, None, str(value), param.unit)
        else:
            converted = float(value) if param.unit in ("count", "score") else _to_unit(float(value), printed, param.unit)
            if converted is None:
                return
            m = Measurement(organ, param_key, side, converted, None, param.unit)
        self.values.setdefault((organ, param_key, side), m)

    def finish(self) -> list[Measurement]:
        for organ, largest_sides in self.nodules.items():
            self.add(organ, "nodule_max_mm", "", max(largest_sides), "mm")
        for organ, count in self.nodule_counts.items():
            self.add(organ, "nodule_count", "", count)
        for organ, score in self.tirads.items():
            self.add(organ, "tirads", "", score)
        return list(self.values.values())


def _dims(out: _Collector, organ: str | None, side: str, m: re.Match) -> None:
    nums = [_num(n) for n in re.findall(_NUM, m.group(0))]
    unit = m.group(m.lastindex)
    if len(nums) == 3:
        longest = nums.index(max(nums))
        rest = [n for i, n in enumerate(nums) if i != longest]
        named = [("length", nums[longest]), ("width", rest[0]), ("thickness", rest[1])]
    else:
        named = [("length", nums[0]), ("width", nums[1])]
    params = ORGANS[organ].params if organ else ()
    for name, value in named:
        param = next((p for p in params if p.key.startswith(name + "_") and p.unit in ("mm", "cm")), None)
        if param:
            out.add(organ, param.key, side, value, unit)


def _clause(out: _Collector, organ: str | None, side: str, nodule: bool, lesion: bool, clause: str) -> None:
    for key in _QUALITIES:
        q = _QUALITY_AFTER[key].search(clause) or _QUALITY_BEFORE[key].search(clause)
        if q:
            out.add(organ, key, side, q.group(1))
    for t in _TIRADS.finditer(clause):
        if organ:
            out.tirads[organ] = max(out.tirads.get(organ, 0), int(t.group(1)))
        clause = _blank(clause, t)
    if organ:
        for c in _NODULE_COUNT.finditer(clause):
            if c.group(1) is None or _count_agrees(int(c.group(1)), c.group(2)):
                out.nodule_counts.setdefault(organ, int(c.group(1) or c.group(3)))
                clause = _blank(clause, c)
                break
    if nodule and organ:
        for d in _DIMS.finditer(clause):
            nums = [_num(n) for n in re.findall(_NUM, d.group(0))]
            mm = _to_unit(max(nums), d.group(d.lastindex), "mm")
            if mm is not None:
                out.nodules.setdefault(organ, []).append(mm)
            clause = _blank(clause, d)
        return
    for d in _DIMS.finditer(clause):
        if not lesion:  # a cyst's or stone's dimensions are never the organ's size
            _dims(out, organ, side, d)
        clause = _blank(clause, d)
    for pattern, param_key in ((_ISTHMUS, "isthmus_mm"), (_PARENCHYMA, "parenchyma_mm")):
        if p := pattern.search(clause):
            out.add(organ, param_key, side, _num(p.group(1)), p.group(2))
            clause = _blank(clause, p)
    for p in _PANCREAS_PART.finditer(clause):
        part = next(v for k, v in _PART_PARAM.items() if p.group(1).startswith(k))
        out.add(organ, part, side, _num(p.group(2)), p.group(3))
        clause = _blank(clause, p)
    for v in _VOL_VALUE.finditer(clause):
        if not lesion:
            _volume(out, organ, side, clause[:v.start()], _num(v.group(1)), v.group(2))
        clause = _blank(clause, v)
    lin = list(_LIN_VALUE.finditer(clause))
    if _WALL.search(clause) and lin:
        out.add(organ, "wall_thickness_mm", side, _num(lin[0].group(1)), lin[0].group(2))
    elif len(lin) == 1 and organ in _SINGLE_SIZE and _is_bare_size(_blank(clause, lin[0])):
        out.add(organ, _SINGLE_SIZE[organ], side, _num(lin[0].group(1)), lin[0].group(2))


def _is_bare_size(rest: str) -> bool:
    """True when the clause, minus its one number+unit, names nothing but the organ, side, lobe or 'size'."""
    if _NOT_ORGAN_SIZE.search(rest):
        return False
    return all(_SIZE_CLAUSE_WORD.match(w) for w in re.findall(r"[^\W\d_]+", rest))


def _volume(out: _Collector, organ: str | None, side: str, before: str, value: float, unit: str) -> None:
    if not organ:
        return
    if _RESIDUAL.search(before):
        out.add(organ, "residual_urine_ml", "", value, unit)
        return
    vols = [p for p in ORGANS[organ].params if p.unit in ("cm³", "ml") and p.key != "residual_urine_ml"]
    sided = next((p for p in vols if p.sides), None)
    plain = next((p for p in vols if not p.sides), None)
    target = sided if (sided and side) else plain
    if target:
        out.add(organ, target.key, side, value, unit)


def extract_rule(title: str, text: str) -> Extraction:
    title_organs = organs_in(title)
    organs = list(title_organs)
    current = title_organs[0] if len(title_organs) == 1 else None
    out = _Collector()
    for line in _lines(text):
        # "Right kidney: cyst …. Size 105×48 mm." — the header's side carries to later side-less sentences, but only
        # until a sentence names a side or re-names the organ ("Single kidney …", "Почка …"): then it is unknown.
        line_side, header_len = "", 0
        if header := _HEADER.match(line):
            found = organs_in(header.group(0))
            if found:
                current = found[0]
                if current not in organs:
                    organs.append(current)
                line_side = next((_SIDE_OF.get(s, "") for s in _SIDE.findall(header.group(0))), "")
                header_len = header.end()
        carry = line_side
        for i, sentence in enumerate(re.split(r"(?<=\.)\s+", _clean(line))):
            body = sentence[header_len:] if i == 0 else sentence  # the header itself is not a "later" mention
            names_side = any(_SIDE_OF.get(s) for s in _SIDE.findall(body))
            renames = re.search(_ORGAN_WORD, body) is not None
            side = "" if (renames and not names_side) else carry
            if names_side or renames:
                carry = ""
            nodule, lesion = False, False
            for clause in re.split(r";|,\s+", sentence):
                for s in _SIDE.findall(clause):
                    side = _SIDE_OF.get(s, "")
                nodule = nodule or bool(_NODULE.search(clause))
                lesion = lesion or bool(_LESION.search(clause))
                _clause(out, current, side, nodule, lesion, clause)
    return Extraction(organs=organs, measurements=out.finish())


# ---- AI reading (opt-in): the model only transcribes; the catalog and the unit conversion stay in code ----

MAX_TEXT = 200
_CATALOG = "\n".join(
    f"- {o.key}: " + ", ".join(
        f"{p.key} ({p.unit or 'text'}{', side left/right' if p.sides else ''})" for p in o.params)
    for o in ORGANS.values())
PROMPT = (
    "You read an ultrasound or imaging report (it may be in Russian or English) and copy organ measurements out of "
    "it. Use only these organs and parameters (organ: param (unit)):\n" + _CATALOG + "\n"
    "Rules: use only organ and param keys from the list. Copy only numbers printed in the report; never calculate, "
    "estimate, or interpret. Give the unit exactly as printed (mm, cm, cm3, ml); the program converts. For a parameter "
    "with sides, set side to left or right, else an empty string. For a descriptive (text) parameter give the "
    "report's own wording in text and null for value. Use null for anything the report does not say. Add no "
    "diagnoses or advice."
)
SCHEMA = {
    "type": "object",
    "properties": {"measurements": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "organ": {"type": "string"}, "param": {"type": "string"}, "side": {"type": ["string", "null"]},
            "value": {"type": ["number", "null"]}, "unit": {"type": ["string", "null"]},
            "text": {"type": ["string", "null"]},
        },
        "required": ["organ", "param", "side", "value", "unit", "text"],
    }}},
    "required": ["measurements"],
}


class _Row(BaseModel):
    organ: str
    param: str
    side: str | None = None
    value: float | None = None
    unit: str | None = None
    text: str | None = None


class _ModelOutput(BaseModel):
    measurements: list[_Row]


def _validated(row: _Row) -> Measurement | None:
    """The row as a catalog measurement in catalog units, or None when it does not fit the catalog."""
    param = get_param(row.organ, row.param)
    if param is None:
        return None
    side = (row.side or "").strip().lower()
    if param.sides != (side != "") or side not in SIDES:
        return None
    if param.kind == "text":
        text = (row.text or "").strip()
        return Measurement(row.organ, row.param, side, None, text, param.unit) if text and len(text) <= MAX_TEXT else None
    if row.value is None or not math.isfinite(row.value):
        return None
    if param.unit in ("count", "score"):
        value = float(row.value)
    else:
        value = _to_unit(float(row.value), (row.unit or "").strip().lower(), param.unit)
    if value is None or not math.isfinite(value):
        return None
    return Measurement(row.organ, row.param, side, value, None, param.unit)


class ScanExtractor:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def extract(self, title: str, text: str, document: bytes | None, mime_type: str | None) -> Extraction:
        """Reads the report text when there is any, else the attached file."""
        if text.strip():
            raw = self.client.generate_json(PROMPT, f"{title}\n{text}".encode(), SCHEMA, mime_type="text/plain")
        elif document is not None and mime_type:
            raw = self.client.generate_json(PROMPT, document, SCHEMA, mime_type=mime_type)
        else:
            return Extraction()
        try:
            output = _ModelOutput.model_validate(raw)
        except ValidationError as exc:
            raise ParseError("The AI answer is not shaped like scan measurements.") from exc
        found: dict[tuple[str, str, str], Measurement] = {}
        for row in output.measurements:
            if (m := _validated(row)) is not None:
                found.setdefault((m.organ_key, m.param_key, m.side), m)
        organs = list(dict.fromkeys(m.organ_key for m in found.values()))
        return Extraction(organs=organs, measurements=list(found.values()))
