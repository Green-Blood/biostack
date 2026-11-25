import datetime as dt
import json
import re

import pytest
from starlette.requests import Request

from db.models import Biomarker, LabReport
from services import i18n
from services.briefing import fallback_bullets, get_briefing
from services.briefing_writer import PROMPT, BriefingWriter
from services.clock import local_zone
from services.context_builder import build_context
from services.correlation_phrases import describe
from services.early_warning import assess_risk
from services.graph_builder import build_graph
from services.i18n_messages import EN, RU
from services.markers import marker_display_name

ZONE = local_zone()
NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)


def _request(accept_language: str | None) -> Request:
    headers = [(b"accept-language", accept_language.encode())] if accept_language is not None else []
    return Request({"type": "http", "headers": headers})


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", text))


def test_catalogs_have_the_same_keys_and_placeholders():
    assert set(EN) == set(RU)
    assert {k: _placeholders(v) for k, v in EN.items()} == {k: _placeholders(v) for k, v in RU.items()}


@pytest.mark.parametrize("header,lang", [
    (None, "en"), ("", "en"), ("en", "en"), ("ru", "ru"), ("ru-RU,ru;q=0.9,en;q=0.8", "ru"), ("RU", "ru"),
    ("de", "en"), ("en-US,ru;q=0.5", "en"), ("*", "en"),
])
def test_get_lang_reads_the_first_language_tag(header, lang):
    assert i18n.get_lang(_request(header)) == lang


def test_msg_fills_params_and_falls_back_to_english_for_other_languages():
    assert i18n.msg("en", "http.record_not_found") == "Record not found"
    assert i18n.msg("ru", "http.record_not_found") != "Record not found"
    assert i18n.msg("ru", "http.lab_too_large", mb=25).count("25") == 1
    assert i18n.msg("de", "http.record_not_found") == "Record not found"  # type: ignore[arg-type]


def test_translate_text_maps_known_english_messages_including_templated_ones():
    assert i18n.translate_text("en", "No such keyframe") == "No such keyframe"
    assert i18n.translate_text("ru", "Unknown thing") == "Unknown thing"
    assert i18n.translate_text("ru", "The AI service refused the request (429).") == i18n.msg("ru", "ai.refused", code="429")
    ru = i18n.translate_text("ru", "Add GEMINI_API_KEY to .env to enable this. You can still type the report in.")
    assert "GEMINI_API_KEY" in ru and "You can" not in ru


def test_correlation_phrase_in_russian_keeps_the_same_effect():
    en = describe("pm2_5", "hrv_sdnn", -0.5, 24)
    ru = describe("pm2_5", "hrv_sdnn", -0.5, 24, "ru")
    assert en[1] == ru[1] == "worsens"
    assert en[0] != ru[0] and not re.search("[A-Za-z]{4,}", ru[0].replace("PM2.5", "").replace("HRV", ""))


def test_risk_reason_and_labels_in_russian(session):
    risk = assess_risk(session, NOW, "23:00", ZONE, "ru")
    assert risk.score is None
    assert risk.reason == i18n.msg("ru", "ew.reason", n=0, total=6, min=2)
    assert all(not f.label.isascii() for f in risk.factors)
    assert assess_risk(session, NOW, "23:00", ZONE).factors[0].label == "Falling air pressure"


def test_fallback_briefing_in_russian(session):
    ru = get_briefing(session, NOW, "23:00", ZONE, lambda: None, ai_enabled=False, lang="ru")
    assert ru.label == i18n.msg("ru", "briefing.fallback_label")
    assert ru.bullets[0] == i18n.msg("ru", "briefing.no_score")
    en = get_briefing(session, NOW, "23:00", ZONE, lambda: None, ai_enabled=False)
    assert en.label == "Summary from your data"
    assert en.bullets == fallback_bullets(build_context(session, NOW, "23:00", ZONE))


def test_gemini_prompt_asks_for_russian_only_when_requested():
    class Client:
        prompts: list = []

        def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
            self.prompts.append(prompt)
            return {"bullets": ["a", "b", "c"]}

    client = Client()
    BriefingWriter(client).write({"x": 1})
    BriefingWriter(client).write({"x": 1}, "ru")
    assert client.prompts[0] == PROMPT
    assert client.prompts[1] == PROMPT + " Write the bullets in Russian."


def test_graph_notes_in_russian(session):
    assert build_graph(session, "ru")["notes"] == [i18n.msg("ru", "graph.not_run")]
    assert build_graph(session)["notes"] == ["The analysis has not run yet."]


def test_marker_display_name_prefers_russian_when_known():
    assert marker_display_name("ferritin", "Ferritin", "ru") == "Ферритин"
    assert marker_display_name("ferritin", "Ferritin", "en") == "Ferritin"
    assert marker_display_name("unmapped:foo", "Foo", "ru") == "Foo"
    assert marker_display_name("ferritin", "My own name", "ru") == "Ферритин"


def test_every_catalog_marker_has_a_russian_name():
    from pathlib import Path
    entries = json.loads((Path(__file__).parent.parent / "services" / "marker_aliases.json").read_text(encoding="utf-8"))
    assert all(e.get("display_name_ru") for e in entries)


def test_out_of_range_markers_in_context_use_the_requested_language(session):
    report = LabReport(test_date=dt.date(2026, 3, 1), lab_name="x")
    session.add(report)
    session.commit()
    session.add(Biomarker(report_id=report.id, marker_key="ferritin", display_name="Ferritin", raw_name="Ferritin",
                          value=5.0, unit="ng/mL", ref_min=30.0, ref_max=300.0, is_out_of_range=True))
    session.commit()
    assert build_context(session, NOW, "23:00", ZONE)["out_of_range_biomarkers"][0]["name"] == "Ferritin"
    assert build_context(session, NOW, "23:00", ZONE, "ru")["out_of_range_biomarkers"][0]["name"] == "Ферритин"
