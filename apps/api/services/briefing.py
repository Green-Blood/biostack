"""The daily three-bullet briefing: state of the day, patterns found, preventive steps.

By default it is the deterministic "Summary from your data", built from the trailing-72-hour context with no AI and
no network. Only when the owner has turned on the AI briefing setting is Gemini asked, and then at most once per
day: its answer, or a failure marker, is cached for the day. After a failure the data summary is shown with an
offer to try again; only an explicit refresh asks the AI a second time. A missing key or model is not an attempt
and is not cached, so adding one takes effect at once.
"""
import datetime as dt
import threading
from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session

from db.models import DEMO_SOURCE, AppSetting, BriefingCache
from services.ai_provider import AiNotConfigured
from services.briefing_writer import BriefingWriter
from services.context_builder import build_context
from services.demo_data import demo_counts
from services.gemini_client import AiRequestError
from services.gemini_parser import ParseError
from services.half_life_engine import as_utc
from services.i18n import msg, msg_plural

FALLBACK_LABEL = "Summary from your data"
AI_LABEL = "AI summary"


@dataclass(frozen=True)
class Briefing:
    day: dt.date
    source: str  # "ai" | "fallback"
    label: str
    bullets: list[str]
    can_retry: bool = False  # the AI failed today; an explicit refresh may try once more


def _state_bullet(context: dict, lang: str) -> str:
    risk = context["risk"]
    if risk["score"] is None:
        return msg(lang, "briefing.no_score")
    drivers = [f["label"] for f in sorted(risk["factors"], key=lambda f: f["points"], reverse=True) if f["points"] > 0][:2]
    text = msg(lang, "briefing.risk", score=risk["score"], level=msg(lang, f"level.{risk['level']}"))
    if drivers:
        return msg(lang, "briefing.main_factors", text=text, drivers=", ".join(drivers))
    return msg(lang, "briefing.no_factor", text=text)


def _pattern_bullet(context: dict, lang: str) -> str:
    if not context["correlations"]:
        return msg(lang, "briefing.no_pattern")
    top = context["correlations"][0]
    return msg(lang, "briefing.pattern", phrase=top["phrase"], n_days=top["n_days"])


def _prevention_bullet(context: dict, lang: str) -> str:
    if context["risk"]["recommendations"]:
        return context["risk"]["recommendations"][0]
    caffeine = context["caffeine_left_at_tonights_bedtime_mg"]
    if caffeine > 0:
        return msg(lang, "briefing.caffeine", mg=f"{caffeine:.0f}")
    return msg(lang, "briefing.keep_logging")


def _stale_bullet(context: dict, lang: str) -> list[str]:
    stale = sum(1 for m in context.get("data_age", []) if m["stale"])
    return [msg_plural(lang, "briefing.stale_results", stale)] if stale else []


def _course_bullets(context: dict, lang: str) -> list[str]:
    out = []
    for c in context.get("courses", []):
        if c["status"] == "finished":
            key = "briefing.course_finished" if c["target_marker"] else "briefing.course_finished_plain"
            out.append(msg(lang, key, name=c["name"], date=c["end"], marker=c["target_marker"]))
        elif c["end"]:
            out.append(msg(lang, "briefing.course_active", name=c["name"], start=c["start"], end=c["end"]))
        else:
            out.append(msg(lang, "briefing.course_open", name=c["name"], start=c["start"]))
    return out


def fallback_bullets(context: dict, lang: str = "en") -> list[str]:
    """The three standing bullets, then (only when they apply) one on stale results and one per recent course."""
    return [_state_bullet(context, lang), _pattern_bullet(context, lang), _prevention_bullet(context, lang),
            *_stale_bullet(context, lang), *_course_bullets(context, lang)]


def _stamp(context: dict) -> dict:
    """What a cached AI briefing was written from besides the day: the data age, the courses, and the profile's sex and age.

    Only language-independent facts (marker keys, ids, dates, flags): names change with the request language, and
    switching language must not cost another AI call."""
    age = [{"marker": m["marker_key"], "age_days": m["age_days"], "stale": m["stale"]} for m in context["data_age"]]
    courses = [{"id": c["id"], "status": c["status"], "start": c["start"], "end": c["end"], "marker": c["target_marker_key"]}
               for c in context["courses"]]
    profile = context.get("profile", {})  # corrected sex or age rewrites the day's briefing once; weight does not
    return {"v": 4, "data_age": age, "courses": courses, "sex": profile.get("sex"), "age_years": profile.get("age_years")}


def _stamp_key(day: dt.date) -> str:
    return f"briefing_stamp:{day.isoformat()}"


_attempt_lock = threading.Lock()  # concurrent first loads must not each spend an AI attempt or insert the same day


def _data_summary(context: dict, day: dt.date, lang: str, can_retry: bool = False) -> Briefing:
    return Briefing(day, "fallback", msg(lang, "briefing.fallback_label"), fallback_bullets(context, lang), can_retry)


def _cache_source(session: Session) -> str:
    return DEMO_SOURCE if sum(demo_counts(session).values()) else "real"


def get_briefing(
    session: Session, now: dt.datetime, bedtime: str, zone: dt.tzinfo, writer_factory: Callable[[], BriefingWriter],
    *, ai_enabled: bool, refresh: bool = False, lang: str = "en",
) -> Briefing:
    now = as_utc(now)
    day = now.astimezone(zone).date()
    context = build_context(session, now, bedtime, zone, lang)
    if not ai_enabled:
        return _data_summary(context, day, lang)
    with _attempt_lock:
        cached = session.get(BriefingCache, day, populate_existing=True)
        stamp = _stamp(context)
        row = session.get(AppSetting, _stamp_key(day))
        if cached and not cached.failed and (row is None or row.value != stamp):
            cached = None  # written before the data age or courses changed (or before they were tracked)
        if cached and not refresh:
            return Briefing(day, "ai", msg(lang, "briefing.ai_label"), list(cached.bullets)) if not cached.failed else _data_summary(context, day, lang, True)
        try:
            bullets = writer_factory().write(context, lang)
        except AiNotConfigured:
            return _data_summary(context, day, lang)
        except (AiRequestError, ParseError):
            session.merge(BriefingCache(briefing_date=day, bullets=[], failed=True, source=_cache_source(session)))
            session.merge(AppSetting(key=_stamp_key(day), value=stamp))
            session.commit()
            return _data_summary(context, day, lang, True)
        session.merge(BriefingCache(briefing_date=day, bullets=bullets, source=_cache_source(session)))
        session.merge(AppSetting(key=_stamp_key(day), value=stamp))
        session.commit()
    return Briefing(day, "ai", msg(lang, "briefing.ai_label"), bullets)
