import datetime as dt

import pytest

from services.gemini_parser import LabParser, ParseError


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_json(self, prompt, pdf_bytes, schema, mime_type="application/pdf"):
        self.calls.append((prompt, pdf_bytes, schema))
        return self.payload


def _payload(**overrides):
    base = {"test_date": "2024-03-01", "lab_name": "Akfa Lab", "results": [
        {"name": "25-OH Vitamin D", "value": 24.0, "unit": "ng/ml", "ref_min": 30, "ref_max": 100, "result_text": None},
    ]}
    return {**base, **overrides}


def test_parse_normalizes_marker_unit_and_date():
    draft = LabParser(FakeClient(_payload())).parse(b"%PDF")
    assert draft.test_date == dt.date(2024, 3, 1) and draft.lab_name == "Akfa Lab"
    row = draft.rows[0]
    assert (row.marker_key, row.display_name, row.unit) == ("vitamin_d_25_oh", "Vitamin D (25-OH)", "ng/mL")
    assert row.mapped is True


def test_out_of_range_is_computed_in_code_not_by_model():
    payload = _payload(results=[
        {"name": "Vitamin D", "value": 24, "unit": "ng/mL", "ref_min": 30, "ref_max": 100,
         "result_text": None, "is_out_of_range": False},
        {"name": "Vitamin D", "value": 50, "unit": "ng/mL", "ref_min": 30, "ref_max": 100, "result_text": None},
        {"name": "Vitamin D", "value": 150, "unit": "ng/mL", "ref_min": None, "ref_max": 100, "result_text": None},
        {"name": "Vitamin D", "value": 5, "unit": "ng/mL", "ref_min": None, "ref_max": None, "result_text": None},
    ])
    flags = [r.is_out_of_range for r in LabParser(FakeClient(payload)).parse(b"%PDF").rows]
    assert flags == [True, False, True, False]


def test_unknown_marker_is_unmapped_and_text_result_kept():
    payload = _payload(results=[{"name": "Mucus", "value": None, "unit": None, "ref_min": None,
                                 "ref_max": None, "result_text": "+"}])
    row = LabParser(FakeClient(payload)).parse(b"%PDF").rows[0]
    assert row.mapped is False and row.marker_key == "unmapped:mucus" and row.value is None
    assert row.result_text == "+" and row.unit == "" and row.is_out_of_range is False


def test_blank_names_are_dropped_and_missing_date_allowed():
    payload = _payload(test_date=None, results=[
        {"name": "  ", "value": 1, "unit": "", "ref_min": None, "ref_max": None, "result_text": None},
        {"name": "Ferritin", "value": 50, "unit": "ng/mL", "ref_min": 30, "ref_max": 400, "result_text": None},
    ])
    draft = LabParser(FakeClient(payload)).parse(b"%PDF")
    assert draft.test_date is None and [r.name for r in draft.rows] == ["Ferritin"]


@pytest.mark.parametrize("bad", [
    {"results": "nope"},
    {"test_date": "not a date", "results": []},
    {"results": [{"name": "X", "value": "abc"}]},
    ["not", "an", "object"],
])
def test_bad_model_output_raises_parse_error(bad):
    with pytest.raises(ParseError):
        LabParser(FakeClient(bad)).parse(b"%PDF")


def test_client_receives_prompt_pdf_and_schema():
    client = FakeClient(_payload())
    LabParser(client).parse(b"%PDF-bytes")
    prompt, pdf, schema = client.calls[0]
    assert pdf == b"%PDF-bytes" and "lab" in prompt.lower()
    assert set(schema["properties"]) == {"test_date", "lab_name", "results"}
