"""Things the AI offered to record. A proposal is validated with the same input models the normal forms use and
stored on the message as 'pending'; it is written to the record only when the person confirms it."""
import datetime as dt
import logging

from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session

from routers import journal, profile, records, supplements
from services import clock, profile as profile_service
from services.app_settings import configured_zone
from services.gemini_client import ToolCall
from services.i18n import msg

log = logging.getLogger("chat_actions")

PENDING, DONE, DISMISSED, FAILED = "pending", "done", "dismissed", "failed"


def _day(value: object, fallback: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value)) if value else fallback
    except ValueError:
        return fallback


def _clean(args: dict, *keys: str) -> dict:
    return {k: args[k] for k in keys if args.get(k) not in (None, "")}


def _measurement(args: dict, today: dt.date):
    body = profile.MeasurementIn(date=_day(args.get("date"), today), kind=args.get("kind"), value=args.get("value"))
    if body.kind not in profile_service.KINDS or not profile_service.VALUE_RANGE[body.kind][0] <= body.value <= profile_service.VALUE_RANGE[body.kind][1]:
        raise ValueError("invalid measurement")
    return body, "chat.act_measurement", {"kind": body.kind, "value": f"{body.value:g}", "date": body.date.isoformat()}


def _visit(args: dict, today: dt.date):
    body = records.RecordIn(record_type=args.get("record_type") or "visit", title=args.get("title") or "",
                            date=_day(args.get("date"), today),
                            **_clean(args, "doctor_name", "clinic_name", "department", "reason", "details"))
    if not body.title.strip():
        raise ValueError("a visit needs a title")
    return body, "chat.act_visit", {"type": body.record_type, "title": body.title.strip(), "date": body.date.isoformat()}


def _journal(args: dict, today: dt.date):
    body = journal.EntryIn(entry_date=_day(args.get("entry_date"), today),
                           **_clean(args, "title", "category", "description", "severity_1_10", "body_location"))
    return body, "chat.act_journal", {"category": body.category, "title": body.title, "date": body.entry_date.isoformat()}


def _supplement(args: dict, today: dt.date):
    body = supplements.QuickLog(**_clean(args, "item_name", "dosage", "unit", "category"))
    dose = f" {body.dosage:g} {body.unit}".rstrip() if body.dosage else ""
    return body, "chat.act_supplement", {"item": body.item_name, "dose": dose}


# name -> (builds the validated input + label, the function that writes it)
_ACTIONS = {
    "add_body_measurement": (_measurement, lambda s, b, lang: profile.add_measurement(b, s, lang)),
    "log_visit": (_visit, lambda s, b, lang: records.create_record(b, s, lang)),
    "add_journal_entry": (_journal, lambda s, b, lang: journal.create_entry(b, s)),
    "log_supplement": (_supplement, lambda s, b, lang: supplements.quick_log(b, s)),
}
_INPUTS = {"add_body_measurement": profile.MeasurementIn, "log_visit": records.RecordIn,
           "add_journal_entry": journal.EntryIn, "log_supplement": supplements.QuickLog}


def propose(session: Session, calls: tuple[ToolCall, ...], lang: str) -> list[dict]:
    """The model's tool calls that pass validation, as pending actions. Anything invalid is dropped, not stored."""
    today = clock.today(configured_zone(session))
    actions = []
    for call in calls:
        if call.name not in _ACTIONS:
            continue
        try:
            body, key, params = _ACTIONS[call.name][0](call.args, today)
        except (ValidationError, ValueError, TypeError):
            log.info("Dropped an invalid %s proposal", call.name)
            continue
        actions.append({"id": f"a{len(actions) + 1}", "name": call.name, "args": body.model_dump(mode="json"),
                        "label": msg(lang, key, **params), "status": PENDING, "result": ""})
    return actions


def execute(session: Session, action: dict, lang: str) -> dict:
    """Writes one confirmed action and returns it with its new status. A refusal (say, an out-of-range weight)
    is kept as a 'failed' action with the reason, never raised."""
    body = _INPUTS[action["name"]].model_validate(action["args"])
    try:
        _ACTIONS[action["name"]][1](session, body, lang)
    except HTTPException as exc:
        session.rollback()
        return {**action, "status": FAILED, "result": str(exc.detail)}
    return {**action, "status": DONE, "result": msg(lang, "chat.action_done")}
