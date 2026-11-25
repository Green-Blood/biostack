"""Asks Gemini for the three briefing bullets and checks the answer has exactly that shape."""
import json

from services.gemini_client import GeminiClient
from services.gemini_parser import ParseError

BULLET_COUNT = 3

PROMPT = (
    "You write a short daily health briefing for one person from the JSON of their last 72 hours. Return exactly 3 "
    "bullets: (1) the state of the day, (2) correlations found in their own data, (3) preventive steps for today. "
    "Use only numbers that appear in the JSON, give no diagnoses, and say so plainly when data is missing. Each "
    "bullet is one or two plain sentences with no statistical jargon (no r, p or correlation coefficients). In "
    "data_age, a result marked stale is older than its suggested re-test interval: treat it as outdated, say so "
    "plainly, never present it as current, and mention how old it is. "
    "If a profile is present, its facts (age, sex, height, weight, BMI) are context only: read lab results against the "
    "reference ranges printed on the report, and do not diagnose. Profile values carry dates (weight_date is when the "
    "weight was measured): treat an old weight as old."
)
LANGUAGE_NOTES = {"ru": " Write the bullets in Russian."}  # English is the default and adds nothing
SCHEMA = {
    "type": "object",
    "properties": {
        "bullets": {"type": "array", "items": {"type": "string"}, "minItems": BULLET_COUNT, "maxItems": BULLET_COUNT},
    },
    "required": ["bullets"],
}


class BriefingWriter:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def write(self, context: dict, lang: str = "en") -> list[str]:
        raw = self.client.generate_json(PROMPT + LANGUAGE_NOTES.get(lang, ""), json.dumps(context).encode(), SCHEMA, mime_type="application/json")
        bullets = raw.get("bullets") if isinstance(raw, dict) else None
        if not isinstance(bullets, list) or len(bullets) != BULLET_COUNT or not all(
            isinstance(b, str) and b.strip() for b in bullets
        ):
            raise ParseError("The AI answer is not three bullets.")
        return [b.strip() for b in bullets]
