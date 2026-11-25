"""Sex- and age-qualified reference ranges printed on one result row, and the choice among them by profile.

"М. 130-160 Ж. 120-140" or "до 60 лет 10.0 - 25.0 старше 60 лет 10.0 - 21.0" give several candidates. A candidate is
chosen only when the profile decides it unambiguously; otherwise the range stays blank (never guessed).
"""
import dataclasses
import re

_N = r"\d+(?:[.,]\d+)?"
_AGE_WORD = r"(?:лет|года|год|г\.|years?|yrs?)(?![A-Za-zА-Яа-яЁё])"
_TOKENS = (
    ("age_band", re.compile(rf"(?:от\s+)?(?P<lo>\d+)\s*(?:-|–|до|to)\s*(?P<hi>\d+)\s*{_AGE_WORD}", re.I)),
    ("age_under", re.compile(rf"(?:до|младше|менее|under|below)\s*(?P<n>\d+)\s*{_AGE_WORD}", re.I)),
    ("age_over", re.compile(rf"(?:(?:старше|свыше|более|over|above)\s*(?P<n>\d+)(?:\s*{_AGE_WORD})?|от\s*(?P<m>\d+)\s*{_AGE_WORD})(?:\s+и\s+старше)?", re.I)),
    ("adult", re.compile(r"взросл\w*|adults?\b", re.I)),
    ("child", re.compile(r"дет(?:и|ей|ям|ск\w*)\b|child(?:ren)?\b", re.I)),
    ("female", re.compile(r"(?<![А-Яа-яЁё])Ж(?:\.|(?=:))|жен\.?(?=\s|:|$)|женщин\w*|\bF\b\.?|female", re.I)),
    ("male", re.compile(r"(?<![А-Яа-яЁё])М(?:\.|(?=:))|муж\.?(?=\s|:|$)|мужчин\w*|\bM\b\.?|\bmale", re.I)),
)
_RANGE = re.compile(rf"\s*[:\-–]?\s*(?P<a>{_N})\s*(?:-|–|—|до)\s*(?P<b>{_N})")


@dataclasses.dataclass(frozen=True)
class RangeCandidate:
    ref_min: float
    ref_max: float
    sex: str | None = None
    age_min: int | None = None
    age_max: int | None = None


def _num(token: str) -> float:
    return float(token.replace(",", "."))


def _tokens(text: str) -> list[tuple[int, int, dict]]:
    """Qualifier tokens by position; where two overlap the longer one wins."""
    found: list[tuple[int, int, dict]] = []
    for kind, pattern in _TOKENS:
        for m in pattern.finditer(text):
            if kind == "age_band":
                info = {"age_min": int(m.group("lo")), "age_max": int(m.group("hi"))}
            elif kind == "age_under":
                info = {"age_max": int(m.group("n")) - 1}
            elif kind == "age_over":
                info = {"age_min": int(m.group("n") or m.group("m"))}
            elif kind == "adult":
                info = {"age_min": 18}
            elif kind == "child":
                info = {"age_max": 17}
            else:
                info = {"sex": kind}
            found.append((m.start(), m.end(), info))
    found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
    out: list[tuple[int, int, dict]] = []
    for token in found:
        if not out or token[0] >= out[-1][1]:
            out.append(token)
    return out


_FREE_RANGE = re.compile(rf"(?<![\d.,])(?P<a>{_N})\s*(?:-|–|—)\s*(?P<b>{_N})(?![\d])")
_UNIT_GAP = re.compile(r"\s*(?:[^\s\d,;]\S{0,19}\s*)?[,;/]?\s*")  # between ranges: a separator, maybe the unit just printed
_PLAIN_GAP = re.compile(r"\s*(?:\S{1,20}\s*)?[,;]\s*")  # a default range must be set off from the qualified ones by a comma
# words that qualify a range in ways this module does not model: never choose past them
UNMODELLED = re.compile(r"менопауз|беремен|триместр|\bфаз|овуляц|фолликул|лютеин|менструал|климакс|курящ|"
                        r"pregnan|trimester|menopaus|luteal|follicular|ovulat|\bphase", re.I)


def analyze(text: str) -> tuple[list[RangeCandidate], bool]:
    """(candidates, undecidable). Undecidable: the line has qualified ranges but cannot be read unambiguously (a range
    without a qualifier directly before it, a qualifier without a range, or words we do not model between them);
    then there are no candidates and the range must stay blank."""
    tokens = _tokens(text)
    if not tokens:
        return [], False
    chains: list[list[tuple[int, int, dict]]] = []
    for token in tokens:
        if chains and re.fullmatch(r"[\s,;/]*", text[chains[-1][-1][1]:token[0]]):
            chains[-1].append(token)  # "Женщины старше 30 лет": one qualifier made of two tokens
        else:
            chains.append([token])
    out: list[RangeCandidate] = []
    spans: list[tuple[int, int]] = [(t[0], t[1]) for t in tokens]
    prev_end: int | None = None
    plain: RangeCandidate | None = None
    for position, chain in enumerate(chains):
        rng = _RANGE.match(text, chain[-1][1])
        if rng is None:
            return [], True
        info: dict = {}
        for _, _, part in chain:
            info.update(part)
        gap = text[prev_end if prev_end is not None else 0:chain[0][0]]
        if UNMODELLED.search(gap) or not _UNIT_GAP.fullmatch(gap):
            if position == 0 and prev_end is None:
                free = [m for m in _FREE_RANGE.finditer(gap)]
                if len(free) == 1 and _PLAIN_GAP.fullmatch(gap[free[0].end():]) and not UNMODELLED.search(gap[:free[0].start()]) \
                        and not re.search(r"[A-Za-zА-Яа-яЁё]{3,}", gap[:free[0].start()]):
                    plain = RangeCandidate(_num(free[0].group("a")), _num(free[0].group("b")))
                    out.append(plain)
                    spans.append((rng.start("a"), rng.end("b")))
                    out.append(RangeCandidate(_num(rng.group("a")), _num(rng.group("b")), **info))
                    prev_end = rng.end()
                    continue
            return [], True
        out.append(RangeCandidate(_num(rng.group("a")), _num(rng.group("b")), **info))
        spans.append((rng.start("a"), rng.end("b")))
        prev_end = rng.end()
    for m in _FREE_RANGE.finditer(text):
        inside_known = any(s <= m.start() < e or s < m.end() <= e for s, e in spans)
        if not inside_known and not (plain is not None and m.start() < chains[0][0][0]):
            return [], True  # a range with no qualifier directly before it
    return out, False


def extract_candidates(text: str) -> list[RangeCandidate]:
    """Qualified ranges in `text`, or none when the line is undecidable (see `analyze`)."""
    return analyze(text)[0]


def _fit(value: int | str | None, known: int | str | None, test) -> str:
    """"n/a" when the candidate says nothing on this dimension, "unknown" when the profile lacks it, else match/mismatch."""
    if value is None:
        return "n/a"
    if known is None:
        return "unknown"
    return "match" if test(known) else "mismatch"


def select_candidate(candidates: list[RangeCandidate], sex: str | None, age: int | None) -> tuple[tuple[float, float] | None, str | None]:
    """((ref_min, ref_max) or None, needs_profile). needs_profile is "sex" | "age" | "both" when a missing profile
    field is what kept the range blank."""
    definite: set[tuple[float, float]] = set()
    undecided: list[tuple[RangeCandidate, set[str]]] = []
    for c in candidates:
        by_sex = _fit(c.sex, sex, lambda s: s == c.sex)
        by_age = _fit(c.age_min if c.age_min is not None else c.age_max, age,
                      lambda a: (c.age_min is None or a >= c.age_min) and (c.age_max is None or a <= c.age_max))
        if "mismatch" in (by_sex, by_age):
            continue
        missing = {name for name, fit in (("sex", by_sex), ("age", by_age)) if fit == "unknown"}
        if missing:
            undecided.append((c, missing))
        else:
            definite.add((c.ref_min, c.ref_max))
    if len(definite) == 1 and not undecided:
        return next(iter(definite)), None
    missing_all = set().union(*(m for _, m in undecided)) if undecided else set()
    needs = None if not missing_all else "both" if missing_all == {"sex", "age"} else next(iter(missing_all))
    return None, needs
