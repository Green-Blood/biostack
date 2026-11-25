"""Deterministic stand-in for Gemini. Reachable only with BIOSTACK_FAKE_AI=1 and APP_ENV=test."""
from services.gemini_client import PDF, ChatReply, ToolCall


class FakeGeminiClient:
    def generate_json(self, prompt: str, document: bytes, schema: dict, mime_type: str = PDF) -> dict:
        if "bullets" in schema["properties"]:
            return {"bullets": ["Test briefing: state of the day.", "Test briefing: patterns.", "Test briefing: next steps."]}
        if "measurements" in schema["properties"]:
            return {"measurements": [
                {"organ": "thyroid", "param": "volume_total", "side": "", "value": 10.5, "unit": "cm3", "text": None},
                {"organ": "thyroid", "param": "made_up", "side": "", "value": 1, "unit": "mm", "text": None},
                {"organ": "kidneys", "param": "length_cm", "side": "left", "value": 98, "unit": "mm", "text": None},
            ]}
        if "summary" in schema["properties"]:
            return {"summary": "No acute abnormality.", "findings": ["Lungs are clear.", "No pleural effusion."]}
        return {
            "test_date": "2025-06-15",
            "lab_name": "Sample Lab",
            "results": [
                {"name": "25-OH Vitamin D", "value": 28.0, "unit": "ng/ml", "ref_min": 30, "ref_max": 100,
                 "result_text": None},
                {"name": "Ferritin", "value": 52.0, "unit": "ng/mL", "ref_min": 30, "ref_max": 400,
                 "result_text": None},
                {"name": "Urine mucus", "value": None, "unit": None, "ref_min": None, "ref_max": None,
                 "result_text": "+"},
            ],
        }

    def generate_grounded(self, prompt: str, document: bytes, mime_type: str = "application/json") -> str:
        if "one lab panel" in prompt:
            return ('{"markers": [{"key": "ferritin", "meaning": "Iron stores.", "if_off": "Blood loss or low intake.", '
                    '"action": "Eat red meat."}], "tests_worth_it": [{"name": "Transferrin saturation", "why": "Pairs with ferritin."}], '
                    '"tests_skip": [{"name": "Total iron alone", "why": "Swings through the day."}]}')
        if "one lab marker" in prompt:
            return ('{"meaning": "Iron stores.", "if_high": "Inflammation.", "if_low": "Low intake.", "action": "Eat red meat.", '
                    '"tests_worth_it": [{"name": "Transferrin saturation", "why": "Pairs with ferritin."}]}')
        return ('{"summary": "Test summary.", "actions": [{"title": "Sleep", "detail": "Aim for 8 hours."}], '
                '"tests_worth_it": [{"name": "hs-CRP", "why": "Tracks inflammation."}]}')

    def generate_text(self, system: str, context: str, question: str, image: bytes | None = None,
                      image_mime: str | None = None, history=None, tools=None) -> ChatReply:
        if question.lower().startswith("log weight "):
            try:
                weight = float(question[11:].strip())
                return ChatReply(text="", calls=(ToolCall("add_body_measurement", {"kind": "weight", "value": weight}),))
            except ValueError:
                pass
        return ChatReply(text="Test answer: this is a fixed reply.", input_tokens=100, cached_tokens=0, output_tokens=10)

    def stream_text(self, *args, **kwargs):
        reply = self.generate_text(*args, **kwargs)
        for word in reply.text.split(" "):
            yield word + " "
        yield reply

    def transcribe(self, audio: bytes, mime_type: str) -> str:
        return "Test transcript: how is my ferritin?"
