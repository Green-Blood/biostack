"""Read the text of an imaging report (PDF or photo) into a draft summary and findings for the owner to edit."""
from pydantic import BaseModel, ValidationError

from services.gemini_client import GeminiClient
from services.gemini_parser import ParseError

PROMPT = (
    "You read a radiology or imaging report (it may be in Russian or English). Give the conclusion or impression "
    "as a short summary in the report's own language, and list each distinct finding as one short line. Copy what "
    "the report says; never add interpretation, diagnoses or advice of your own. Use null or an empty list when "
    "the report does not say."
)

SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": ["string", "null"]}, "findings": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary", "findings"],
}


class _ModelOutput(BaseModel):
    summary: str | None = None
    findings: list[str]


class ReportText(BaseModel):
    summary_text: str
    findings_text: str


class ReportReader:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def read(self, document: bytes, mime_type: str) -> ReportText:
        raw = self.client.generate_json(PROMPT, document, SCHEMA, mime_type=mime_type)
        try:
            output = _ModelOutput.model_validate(raw)
        except ValidationError as exc:
            raise ParseError("The AI answer is not shaped like an imaging report.") from exc
        lines = [line.strip() for line in output.findings if line.strip()]
        return ReportText(summary_text=(output.summary or "").strip(), findings_text="\n".join(lines))
