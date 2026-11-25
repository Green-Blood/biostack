"""AI guides built from the stored lab results: one per body-system panel, and the dashboard health summary.

Both ask Gemini with Google Search on, so the advice reflects current guidance. An answer is cached in AppSetting under
a hash of what it was written from: the AI is asked again only when the results change (the dashboard also once a day,
to pick up new research) or on an explicit refresh. The health percentage itself is plain arithmetic, never AI.
"""
import datetime as dt
import hashlib
import json
import logging

from sqlmodel import Session

from db.models import AppSetting
from routers.labs import list_biomarkers
from services.context_builder import profile_context
from services.gemini_client import GeminiClient
from services.gemini_parser import ParseError

COMMON = (
    "Search the web for current guidance. Be practical and specific: foods, supplements with typical doses, sleep, training, "
    "what to ask a doctor. Give no diagnoses and say when a cause needs a doctor. Use only the numbers in the JSON. "
    "Reply with ONLY one JSON object of the stated shape, with no markdown fences. "
)
SYSTEM_PROMPT = COMMON + (
    "You get the JSON of one lab panel ('markers': latest value, reference range, status, past values), the person's profile "
    "and 'already_tested' (every marker they have results for). Shape: "
    '{"markers":[{"key":str,"meaning":str,"typical_range":str,"if_off":str,"action":str}],'
    '"tests_worth_it":[{"name":str,"why":str}],"tests_skip":[{"name":str,"why":str}]}. '
    "Per marker: meaning = what it is, one sentence; typical_range = when ref_min and ref_max are null, search for the usual "
    "adult range for this person's sex and age with its unit, otherwise an empty string; if_off = the likely reasons it is high or low (for an in-range result, "
    "what would push it either way); action = what to do to raise it if low or lower it if high (or keep it steady). "
    "tests_worth_it = up to 5 further tests that pair with this panel and are not in already_tested, each with why it helps "
    "this person; tests_skip = up to 3 popular tests not worth paying for here, with why. Short plain sentences."
)
OVERVIEW_PROMPT = COMMON + (
    "You get the JSON of a person's lab picture: 'health_pct' (the share of markers in range), per-system counts, the "
    "markers out of range, the stale ones and their profile. Shape: "
    '{"summary":str,"actions":[{"title":str,"detail":str}],"tests_worth_it":[{"name":str,"why":str}]}. '
    "summary = two sentences on where they stand. actions = the 3 to 5 steps that would raise health_pct the most, most "
    "impactful first. tests_worth_it = up to 4 tests not in already_tested that would add real information."
)
MARKER_PROMPT = COMMON + (
    "You get the JSON of one lab marker ('marker': latest value, reference range, status, past values), the person's profile "
    "and 'already_tested'. Shape: "
    '{"meaning":str,"typical_range":str,"if_high":str,"if_low":str,"action":str,"tests_worth_it":[{"name":str,"why":str}]}. '
    "The marker may have only a text result (result_text) or no reference range: then identify it from its name and search for "
    "the usual adult range for this person's sex and age, with its unit, in typical_range (otherwise an empty string). "
    "meaning = what it is and why it is measured; if_high and if_low = the likely reasons; action = what to do to move it the "
    "right way given its current status (or keep it steady); tests_worth_it = up to 3 related tests not in already_tested. "
    "Short plain sentences."
)
LANGUAGE_NOTES ={"ru": " Write every text value in Russian."}


log = logging.getLogger(__name__)


def _parse(text: str) -> dict:
    """The first JSON object in the text: search-backed answers sometimes wrap it in prose or code fences."""
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            data, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    log.warning("AI answer without usable JSON, first 300 chars: %r", text[:300])
    raise ParseError("The AI answer is not the expected JSON.")


def _status(m: dict) -> str:
    if m["latest_value"] is None:
        return "text result only"
    if not m["out_of_range_latest"]:
        return "in range"
    v, lo, hi = m["latest_value"], m["ref_min"], m["ref_max"]
    return "low" if lo is not None and v < lo else "high" if hi is not None and v > hi else "out of range"


def _view(m: dict) -> dict:
    return {"key": m["marker_key"], "name": m["display_name"], "value": m["latest_value"], "result_text": m["latest_text"],
            "unit": m["unit"], "ref_min": m["ref_min"], "ref_max": m["ref_max"], "status": _status(m),
            "past_values": m["spark"][:-1], "age_days": m["age_days"]}


def _numeric(session: Session, lang: str) -> list[dict]:
    return [m for m in list_biomarkers(session, lang) if m["latest_value"] is not None and not m["marker_key"].startswith("unmapped:")]


def _answer(session: Session, key: str, payload: dict, prompt: str, lang: str, client: GeminiClient,
            valid, today: dt.date | None, refresh: bool) -> dict:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    stamp = hashlib.sha1((body + (today.isoformat() if today else "")).encode()).hexdigest()
    row = session.get(AppSetting, key)
    if row and row.value.get("stamp") == stamp and not refresh:
        return row.value["data"]
    for attempt in (1, 2):  # one retry: the model occasionally answers in prose or cuts the JSON short
        try:
            data = _parse(client.generate_grounded(prompt + LANGUAGE_NOTES.get(lang, ""), body.encode()))
            if not valid(data):
                raise ParseError("The AI answer is missing parts.")
            break
        except ParseError:
            if attempt == 2:
                raise
    session.merge(AppSetting(key=key, value={"stamp": stamp, "data": data}))
    session.commit()
    return data


def system_guide(session: Session, system: str, lang: str, client: GeminiClient, refresh: bool = False) -> dict | None:
    """None when the panel has no numeric results."""
    rows = _numeric(session, lang)
    panel = [_view(m) for m in rows if m["system"] == system]
    if not panel:
        return None
    payload = {"panel": system, "markers": panel, "already_tested": sorted(m["display_name"] for m in rows), "profile": profile_context(session)}
    return _answer(session, f"insight:system:{system}:{lang}", payload, SYSTEM_PROMPT, lang, client,
                   lambda d: isinstance(d.get("markers"), list), None, refresh)


def marker_guide(session: Session, key: str, lang: str, client: GeminiClient, refresh: bool = False) -> dict | None:
    """None when the marker is unknown. Text-only and unmapped markers count: the AI identifies them from the name."""
    all_rows = list_biomarkers(session, lang)
    marker = next((m for m in all_rows if m["marker_key"] == key), None)
    if marker is None:
        return None
    payload = {"marker": _view(marker), "already_tested": sorted(m["display_name"] for m in all_rows), "profile": profile_context(session)}
    return _answer(session, f"insight:marker:{key}:{lang}", payload, MARKER_PROMPT, lang, client,
                   lambda d: isinstance(d.get("meaning"), str), None, refresh)


def health_pct(rows: list[dict]) -> int | None:
    return round(100 * sum(not m["out_of_range_latest"] for m in rows) / len(rows)) if rows else None


def overview(session: Session, lang: str, client: GeminiClient | None, today: dt.date, refresh: bool = False) -> dict:
    """The health percentage always; the AI part only when a client is given and there are results to read."""
    rows = _numeric(session, lang)
    out = {"health_pct": health_pct(rows), "ok": sum(not m["out_of_range_latest"] for m in rows), "total": len(rows)}
    if client is None or not rows:
        return out
    systems: dict[str, list[int]] = {}
    for m in rows:
        ok_total = systems.setdefault(m["system"], [0, 0])
        ok_total[0] += not m["out_of_range_latest"]
        ok_total[1] += 1
    payload = {"health_pct": out["health_pct"], "systems": {k: {"in_range": v[0], "total": v[1]} for k, v in systems.items()},
               "out_of_range": [_view(m) for m in rows if m["out_of_range_latest"]],
               "stale": [m["display_name"] for m in rows if m["retest_days"] is not None and m["age_days"] > m["retest_days"]],
               "already_tested": sorted(m["display_name"] for m in rows), "profile": profile_context(session)}
    # ponytail: re-asked once a day (to pick up new research), keyed by language only; per-day history if it is ever wanted
    data = _answer(session, f"insight:overview:{lang}", payload, OVERVIEW_PROMPT, lang, client,
                   lambda d: isinstance(d.get("summary"), str) and isinstance(d.get("actions"), list), today, refresh)
    return {**out, **data}
