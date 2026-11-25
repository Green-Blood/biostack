"""Turn a lab PDF into a reviewable draft: AI extracts raw rows, code normalizes and flags them."""
import datetime as dt

from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from services.gemini_client import PDF, GeminiClient
from services.lab_rows import DraftRow, LabRow, resolve_row

PROMPT = (
    "You read a laboratory report (it may be in Russian or English). Extract the test date, the laboratory "
    "name and every result row exactly as printed. Use the date the sample was taken or the result was issued, "
    "formatted YYYY-MM-DD. For each row give the marker name as printed, the numeric value, the unit, and the "
    "numeric reference minimum and maximum when printed (null otherwise). Put non-numeric results such as "
    "'negative' or '+' in result_text and leave value null. Never invent or estimate values; use null when "
    "something is not on the page."
)

_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_STRING = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "test_date": _NULLABLE_STRING,
        "lab_name": _NULLABLE_STRING,
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "value": _NULLABLE_NUMBER, "unit": _NULLABLE_STRING,
                    "ref_min": _NULLABLE_NUMBER, "ref_max": _NULLABLE_NUMBER, "result_text": _NULLABLE_STRING,
                },
                "required": ["name", "value", "unit", "ref_min", "ref_max", "result_text"],
            },
        },
    },
    "required": ["test_date", "lab_name", "results"],
}


class ParseError(Exception):
    """The model's output does not have the shape of a lab report."""


class _ModelOutput(BaseModel):
    test_date: dt.date | None = None
    lab_name: str | None = None
    results: list[LabRow]


class ParsedLab(BaseModel):
    test_date: dt.date | None
    lab_name: str
    rows: list[DraftRow]


class LabParser:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def parse(self, document: bytes, session: Session | None = None, mime_type: str = PDF) -> ParsedLab:
        raw = self.client.generate_json(PROMPT, document, SCHEMA, mime_type)
        try:
            output = _ModelOutput.model_validate(raw)
        except ValidationError as exc:
            raise ParseError("The AI answer is not shaped like a lab report.") from exc
        rows = [resolve_row(r, session) for r in output.results if r.name.strip()]
        return ParsedLab(test_date=output.test_date, lab_name=(output.lab_name or "").strip(), rows=rows)
