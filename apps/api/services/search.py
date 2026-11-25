"""Global search over the owner's own data. Local, read-only, no AI; the query text is never logged.

Matching is case-insensitive, treats ё as е, ignores word order and accepts prefixes ("вит д" finds "Витамин D").
"""
import datetime as dt
import re
from dataclasses import dataclass
from functools import lru_cache

from sqlmodel import Session, select

from db.models import (DEMO_SOURCE, Biomarker, Diagnosis, HealthJournal, ImagingStudy, LabReport, MedicalRecord, Medication,
                       RecordAttachment, MarkerAlias, RecordNote)
from services.i18n import msg
from services.organs import ORGANS, organ_name
from services.markers import _static_index, marker_display_name  # noqa: PLC2701 (same package, shared alias catalog)
from services.queries import effective_dates

KINDS = ("organ", "marker", "signals", "record", "file", "medication", "journal", "imaging")
MIN_QUERY = 2
_KIND_BONUS = {"signals": 6, "organ": 6, "marker": 6, "record": 4, "medication": 3, "imaging": 3, "file": 2, "journal": 2}


def norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", norm(text))


def _all_prefix(q: list[str], words: list[str]) -> bool:
    return bool(q) and all(any(w.startswith(t) for w in words) for t in q)


def match_score(q: list[str], phrase: str, text: str, *, exact_bonus: bool = True) -> int:
    """How well `text` (a title-like string) matches: 100 exact, 90 title starts with the query, 70 all tokens by
    prefix (any order), 0 otherwise."""
    words = tokens(text)
    if not _all_prefix(q, words):
        return 0
    joined = " ".join(words)
    if exact_bonus and joined == phrase:
        return 100
    if joined.startswith(phrase):
        return 90
    return 70


def snippet(q: list[str], *texts: str, width: int = 80) -> str | None:
    """A short excerpt of the first text whose words all start with a query token, around the first hit."""
    for text in texts:
        if not text or not _all_prefix(q, tokens(text)):
            continue
        low = norm(text)
        pos = min((m.start() for m in re.finditer(r"[^\W_]+", low) if any(m.group().startswith(t) for t in q)), default=0)
        start = max(0, pos - width // 3)
        piece = " ".join(text[start:start + width].split())
        return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")
    return None


@dataclass
class _Hit:
    kind: str
    id: int | str
    title: str
    subtitle: str
    href: str
    score: int
    date: dt.date | None = None
    extra: dict | None = None

    def out(self) -> dict:
        return {"kind": self.kind, "id": self.id, "title": self.title, "subtitle": self.subtitle, "href": self.href,
                "score": self.score, **(self.extra or {})}


def _iso(d: dt.date | None) -> str:
    return d.isoformat() if d else ""


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


@lru_cache(maxsize=1)
def _catalog_texts() -> dict[str, list[str]]:
    """marker_key -> every name and alias the catalog knows (English and Russian)."""
    out: dict[str, list[str]] = {}
    from services.markers import _russian_names  # noqa: PLC0415
    for text, match in _static_index().items():
        out.setdefault(match.marker_key, []).append(text)
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    for e in json.loads((Path(__file__).parent / "marker_aliases.json").read_text(encoding="utf-8")):
        out.setdefault(e["marker_key"], []).extend([e["display_name"], *e["aliases"]])
    for key, ru in _russian_names().items():
        out.setdefault(key, []).append(ru)
    return out


def _markers(session: Session, q: list[str], phrase: str, lang: str) -> list[_Hit]:
    eff = effective_dates(session)
    rows: dict[str, list[tuple[Biomarker, dt.date]]] = {}
    for bm, rep in session.exec(select(Biomarker, LabReport).where(Biomarker.report_id == LabReport.id)):
        date = rep.test_date
        if rep.source != "pdf" and rep.record_id and rep.record_id in eff:
            date = eff[rep.record_id][0] or date
        rows.setdefault(bm.marker_key, []).append((bm, date))
    user_aliases: dict[str, list[str]] = {}
    for a in session.exec(select(MarkerAlias)):
        user_aliases.setdefault(a.marker_key, []).extend([a.raw_name, a.display_name])
    catalog = _catalog_texts()
    hits = []
    for key, items in rows.items():
        items.sort(key=lambda t: t[1])
        numeric = [t for t in items if t[0].value is not None]
        bm, date = (numeric or items)[-1]
        title = marker_display_name(key, items[-1][0].display_name, lang)
        names = [title, items[-1][0].display_name, *[b.display_name for b, _ in items], *[b.raw_name for b, _ in items]]
        score = max((match_score(q, phrase, n) for n in names), default=0)
        if not score:
            aliased = [t for t in [*catalog.get(key, []), *user_aliases.get(key, [])] if _all_prefix(q, tokens(t))]
            if aliased:
                score = 60 + (10 if any(" ".join(tokens(t)).startswith(phrase) for t in aliased) else 0)
        if not score:
            continue
        value = "" if bm.value is None else f"{bm.value:g}"
        shown = _join(f"{value} {bm.unit}".strip() if value else (bm.result_text or ""), _iso(date))
        hits.append(_Hit("marker", key, title, shown, f"/biomarkers/{key}", score, date,
                         {"marker_key": key, "value": bm.value, "unit": bm.unit, "date": _iso(date),
                          "out_of_range": bm.is_out_of_range, "is_demo": bm.source == DEMO_SOURCE}))
    return hits


def _field_snippet(q: list[str], lang: str, rec: MedicalRecord, diagnoses: list[Diagnosis], notes: list[RecordNote]):
    """The first private field of a visit or stay that the query matches, worded in the request language."""
    candidates = [("diagnosis", d.name) for d in diagnoses] + [("diagnosis", d.icd10) for d in diagnoses] + [
        ("department", rec.department), ("doctor", rec.doctor_name), ("reason", rec.reason)] + [("note", n.text) for n in notes]
    for field, text in candidates:
        snip = snippet(q, text or "")
        if snip:
            return snip, msg(lang, f"search.field_{field}", text=snip)
    return None, None


def _records(session: Session, q: list[str], phrase: str, lang: str) -> tuple[list[_Hit], dict[int, MedicalRecord]]:
    eff = effective_dates(session)
    recs = {r.id: r for r in session.exec(select(MedicalRecord))}
    diagnoses: dict[int, list[Diagnosis]] = {}
    for d in session.exec(select(Diagnosis)):
        diagnoses.setdefault(d.record_id, []).append(d)
    notes: dict[int, list[RecordNote]] = {}
    for n in session.exec(select(RecordNote)):
        notes.setdefault(n.record_id, []).append(n)
    hits = []
    for r in recs.values():
        date = eff.get(r.id, (r.record_date, False))[0]
        score = match_score(q, phrase, r.title)
        snip = None
        field_label = None
        if not score:
            snip = snippet(q, r.details, r.doctors_note, r.body_markdown)
            score = 30 if snip else 0
        if not score:
            snip, field_label = _field_snippet(q, lang, r, diagnoses.get(r.id, []), notes.get(r.id, []))
            score = 30 if snip else 0
        if not score:
            continue
        type_label = msg(lang, f"search.record_{r.record_type}") if f"search.record_{r.record_type}" in _keys() else r.record_type
        hits.append(_Hit("record", r.id, r.title, field_label or _join(type_label, _iso(date)), f"/records/{r.id}", score, date,
                         {"date": _iso(date), "record_type": r.record_type, "snippet": snip or snippet(q, r.title) or "",
                          "is_demo": r.source == DEMO_SOURCE}))
    return hits, recs


def _keys() -> frozenset[str]:
    from services.i18n_messages import EN  # noqa: PLC0415
    return frozenset(EN)


def _files(session: Session, q: list[str], phrase: str, lang: str, recs: dict[int, MedicalRecord]) -> list[_Hit]:
    hits = []
    for a in session.exec(select(RecordAttachment)):
        score = match_score(q, phrase, a.filename)
        if not score:
            continue
        rec = recs.get(a.record_id)
        hits.append(_Hit("file", a.id, a.filename, msg(lang, "search.file_in", title=rec.title if rec else ""),
                         f"/records/{a.record_id}", score, rec.record_date if rec else None,
                         {"filename": a.filename, "record_id": a.record_id, "record_title": rec.title if rec else "",
                          "is_demo": bool(rec and rec.source == DEMO_SOURCE)}))
    return hits


def _medications(session: Session, q: list[str], phrase: str) -> list[_Hit]:
    hits = []
    for m in session.exec(select(Medication)):
        score = match_score(q, phrase, m.name)
        if not score and snippet(q, m.dosage, m.notes):
            score = 30
        if not score:
            continue
        span = _join(_iso(m.start_date), _iso(m.end_date)) if not (m.start_date and m.end_date) else f"{m.start_date.isoformat()} – {m.end_date.isoformat()}"
        hits.append(_Hit("medication", m.id, m.name, _join(m.dosage, span), "/timeline", score, m.start_date,
                         {"name": m.name, "dosage": m.dosage, "start_date": _iso(m.start_date), "end_date": _iso(m.end_date),
                          "is_demo": m.source == DEMO_SOURCE}))
    return hits


def _journal(session: Session, q: list[str], phrase: str, lang: str) -> list[_Hit]:
    hits = []
    for j in session.exec(select(HealthJournal)):
        score = match_score(q, phrase, j.title)
        snip = None
        if not score:
            snip = snippet(q, j.description)
            score = 30 if snip else 0
        if not score:
            continue
        label = msg(lang, f"search.journal_{j.category}") if f"search.journal_{j.category}" in _keys() else j.category
        hits.append(_Hit("journal", j.id, j.title, _join(label, _iso(j.entry_date)), f"/journal?entry={j.id}", score, j.entry_date,
                         {"date": _iso(j.entry_date), "snippet": snip or "", "is_demo": j.source == DEMO_SOURCE}))
    return hits


def _imaging(session: Session, q: list[str], phrase: str) -> list[_Hit]:
    hits = []
    for s in session.exec(select(ImagingStudy)):
        title = _join(s.study_type, s.body_part)
        score = max(match_score(q, phrase, s.study_type), match_score(q, phrase, s.body_part), match_score(q, phrase, title))
        snip = None
        if not score:
            snip = snippet(q, s.summary_text, s.series_description)
            score = 30 if snip else 0
        if not score:
            continue
        hits.append(_Hit("imaging", s.id, title or s.study_type, _iso(s.study_date), f"/imaging?study={s.id}", score, s.study_date,
                         {"date": _iso(s.study_date), "snippet": snip or "", "is_demo": False}))
    return hits


def _organs(q: list[str], phrase: str, lang: str) -> list[_Hit]:
    """Catalog organs by name (either language) or alias stem; the page may still be empty, it explains how to fill it."""
    hits = []
    for key, organ in ORGANS.items():
        title = organ_name(key, lang)
        score = max(match_score(q, phrase, organ_name(key, lg)) for lg in ("en", "ru"))
        if not score and all(any(t.startswith(a) or a.startswith(t) for a in organ.aliases) for t in q):
            score = 60
        if score:
            hits.append(_Hit("organ", key, title, "", f"/organs/{key}", score))
    return hits


# Body-signals pages. `words` match whole (or, for a query of 4+ letters, as the word's start: "трен" → "тренировки");
# `stems` also match any query word that starts with them ("пульса" → "пульс"). Short words like "сон" are whole
# words only, so "сонография" does not lead to Sleep. The page titles (either language) count as words too.
REVERSE_MIN = 4
SIGNAL_PAGES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "overview": ("/signals", ("тело", "body", "watch", "часы", "samsung"), ("signal", "сигнал", "wearable", "носим")),
    "sleep": ("/signals/sleep", ("сон", "сна", "сну", "спать", "bedtime"),
              ("sleep", "гипнограм", "hypnogram", "засыпан", "пробужд")),
    "heart": ("/signals/heart", ("hrv", "вср", "чсс", "spo2", "spo₂", "heart", "pulse"),
              ("сердц", "сердеч", "пульс", "вариабельн", "variabil", "rmssd", "sdnn", "температур", "temperatur",
               "кислород", "oxygen", "сатурац", "дыхан", "breath", "respirat")),
    "activity": ("/signals/activity", ("бег", "steps", "step"),
                 ("шаги", "шагов", "шаг", "активн", "activit", "тренир", "workout", "training", "exercise", "дистанц",
                  "distance", "калори", "calori", "ходьб", "walking", "running")),
}


def _word_hit(t: str, words, stems) -> bool:
    return (any(t == w or (len(t) >= REVERSE_MIN and w.startswith(t)) for w in words)
            or any(t.startswith(st) or (len(t) >= REVERSE_MIN and st.startswith(t)) for st in stems))


def _signals(q: list[str], phrase: str, lang: str) -> list[_Hit]:
    """Body-signals pages by their name (either language) or a topic word: "сон", "HRV", "пульс", "шаги", "тренировки"."""
    hits = []
    for page, (href, words, stems) in SIGNAL_PAGES.items():
        titles = [tokens(msg(lg, f"search.signals_{page}")) for lg in ("en", "ru")]
        score = 0
        for tw in titles:
            if all(_word_hit(t, tw, ()) for t in q):
                score = max(score, 100 if " ".join(tw) == phrase else 90 if " ".join(tw).startswith(phrase) else 70)
        if not score and all(_word_hit(t, words, stems) for t in q):
            score = 60
        if score:
            hits.append(_Hit("signals", page, msg(lang, f"search.signals_{page}"), msg(lang, "search.signals_section"), href, score))
    return hits


def search(session: Session, query: str, lang: str = "en", limit: int = 6) -> dict:
    q = tokens(query)
    phrase = " ".join(q)
    if len(phrase.replace(" ", "")) < MIN_QUERY:
        return {"query": query, "total": 0, "groups": []}
    limit = max(1, min(limit, 50))
    record_hits, recs = _records(session, q, phrase, lang)
    by_kind = {
        "signals": _signals(q, phrase, lang), "organ": _organs(q, phrase, lang), "marker": _markers(session, q, phrase, lang), "record": record_hits,
        "file": _files(session, q, phrase, lang, recs), "medication": _medications(session, q, phrase),
        "journal": _journal(session, q, phrase, lang), "imaging": _imaging(session, q, phrase),
    }
    groups = []
    for kind in KINDS:
        hits = by_kind[kind]
        for h in hits:
            h.score += _KIND_BONUS[kind]
        hits.sort(key=lambda h: (-h.score, -(h.date.toordinal() if h.date else 0), str(h.id)))
        if hits:
            groups.append({"kind": kind, "total": len(hits), "hits": [h.out() for h in hits[:limit]]})
    return {"query": query, "total": sum(g["total"] for g in groups), "groups": groups}
