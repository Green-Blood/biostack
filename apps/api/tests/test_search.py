import datetime as dt

import pytest
from sqlmodel import Session

from db.models import (Biomarker, HealthJournal, ImagingStudy, LabReport, MedicalRecord, Medication, RecordAttachment)


@pytest.fixture
def data(engine):
    with Session(engine) as s:
        rec = MedicalRecord(title="Визит к урологу", record_type="visit", record_date=dt.date(2023, 5, 1),
                            details="Жалобы на ёмкость мочевого пузыря", doctors_note="наблюдение", source="t", external_id="r1")
        demo = MedicalRecord(title="Demo checkup", record_type="other", record_date=dt.date(2024, 1, 1), source="demo", external_id="d1")
        s.add_all([rec, demo])
        s.flush()
        s.add(RecordAttachment(record_id=rec.id, filename="Анализ крови.pdf", stored_path="attachments/x.pdf",
                               mime_type="application/pdf", size_bytes=3, sha256="a" * 64))
        s.add(Medication(name="Креон", dosage="25000 ЕД", start_date=dt.date(2023, 4, 1), end_date=dt.date(2023, 6, 1)))
        s.add(HealthJournal(entry_date=dt.date(2023, 7, 1), title="Головная боль", description="после ужина, слабость"))
        s.add(ImagingStudy(study_date=dt.date(2022, 2, 2), study_type="MRI", body_part="Brain", summary_text="no acute findings"))
        for key, name, val, unit, src in [("vitamin_d_25_oh", "Vitamin D", 27.6, "ng/mL", "t"), ("iodine_serum", "Iodine", 60, "ug/L", "demo")]:
            rep = LabReport(test_date=dt.date(2024, 3, 1), source=src)
            s.add(rep)
            s.flush()
            s.add(Biomarker(report_id=rep.id, marker_key=key, display_name=name, raw_name=name, value=val, unit=unit,
                            is_out_of_range=key.startswith("vitamin"), source=src))
        s.commit()


def hits(client, q, lang=None, **params):
    headers = {"Accept-Language": lang} if lang else {}
    body = client.get("/api/v1/search", params={"q": q, **params}, headers=headers).json()
    return body, {g["kind"]: g["hits"] for g in body["groups"]}


@pytest.mark.parametrize("q", ["vit d", "витамин д", "25-OH", "VITAMIN D", "d vitamin", "вит"])
def test_vitamin_d_found_by_alias_prefix_and_order(client, data, q):
    _, g = hits(client, q)
    assert g["marker"][0]["marker_key"] == "vitamin_d_25_oh"
    assert g["marker"][0]["href"] == "/biomarkers/vitamin_d_25_oh"
    assert g["marker"][0]["out_of_range"] is True and g["marker"][0]["value"] == 27.6


def test_iodine_in_russian_and_demo_flag(client, data):
    _, g = hits(client, "йод", "ru")
    assert g["marker"][0]["marker_key"] == "iodine_serum"
    assert g["marker"][0]["title"] == "Йод (сыворотка)" and g["marker"][0]["is_demo"] is True


def test_marker_title_uses_request_language(client, data):
    assert hits(client, "vit d", "ru")[1]["marker"][0]["title"].startswith("Витамин")
    assert hits(client, "vit d", "en")[1]["marker"][0]["title"] == "Vitamin D"


def test_yo_matches_ye_in_record_text_and_snippet(client, data):
    _, g = hits(client, "емкость")
    rec = g["record"][0]
    assert rec["title"] == "Визит к урологу" and "ёмкость" in rec["snippet"] and rec["href"] == "/records/1"


def test_record_title_ranks_above_snippet_match(client, engine, data):
    with Session(engine) as s:
        s.add(MedicalRecord(title="Other", details="визит упомянут здесь", source="t", external_id="r9"))
        s.commit()
    _, g = hits(client, "визит")
    assert g["record"][0]["title"] == "Визит к урологу" and g["record"][0]["score"] > g["record"][1]["score"]


def test_files_medications_journal_imaging(client, data):
    assert hits(client, "анализ крови")[1]["file"][0]["record_title"] == "Визит к урологу"
    assert hits(client, "крео")[1]["medication"][0]["name"] == "Креон"
    assert hits(client, "слабость")[1]["journal"][0]["title"] == "Головная боль"
    img = hits(client, "mri")[1]["imaging"][0]
    assert img["href"] == "/imaging?study=1"
    assert hits(client, "acute")[1]["imaging"][0]["snippet"].startswith("no acute")


def test_demo_rows_are_flagged(client, data):
    assert hits(client, "demo")[1]["record"][0]["is_demo"] is True
    assert hits(client, "визит")[1]["record"][0]["is_demo"] is False


@pytest.mark.parametrize("q", ["", " ", "в", "й!"])
def test_short_or_empty_query_returns_nothing(client, data, q):
    body, _ = hits(client, q)
    assert body["groups"] == [] and body["total"] == 0


def test_no_match_is_empty_not_an_error(client, data):
    r = client.get("/api/v1/search", params={"q": "zzzzzz"})
    assert r.status_code == 200 and r.json()["groups"] == []


def test_per_group_cap(client, engine):
    with Session(engine) as s:
        s.add_all(MedicalRecord(title=f"Checkup {i}", source="t", external_id=f"c{i}") for i in range(10))
        s.commit()
    _, g = hits(client, "checkup")
    assert len(g["record"]) == 6
    body, g = hits(client, "checkup", limit=3)
    assert len(g["record"]) == 3 and body["groups"][0]["total"] == 10


def test_subtitle_follows_language(client, data):
    assert hits(client, "визит", "ru")[1]["record"][0]["subtitle"].startswith("Визит")
    assert hits(client, "визит", "en")[1]["record"][0]["subtitle"].startswith("Visit")


def test_search_finds_organ_by_russian_name(client, data):
    _, g = hits(client, "щитовидная", "ru")
    assert g["organ"][0]["id"] == "thyroid" and g["organ"][0]["href"] == "/organs/thyroid"
    assert g["organ"][0]["title"] == "Щитовидная железа"


def test_search_finds_organ_by_english_name_and_alias(client, data):
    assert hits(client, "kidney", "en")[1]["organ"][0]["href"] == "/organs/kidneys"
    assert hits(client, "почки", "en")[1]["organ"][0]["id"] == "kidneys"
    assert "organ" not in hits(client, "vitamin d")[1]


@pytest.mark.parametrize("q, page", [
    ("сон", "sleep"), ("sleep", "sleep"), ("HRV", "heart"), ("вариабельность", "heart"), ("пульс", "heart"),
    ("heart", "heart"), ("температура", "heart"), ("SpO2", "heart"), ("кислород", "heart"), ("дыхание", "heart"),
    ("шаги", "activity"), ("steps", "activity"), ("активность", "activity"), ("тренировки", "activity"),
    ("workouts", "activity"),
])
def test_search_finds_body_signals_pages(client, data, q, page):
    _, g = hits(client, q, "ru")
    hit = g["signals"][0]
    assert hit["id"] == page and all(h["score"] < hit["score"] for h in g["signals"][1:])
    assert hit["href"] == ("/signals" if page == "overview" else f"/signals/{page}")
    assert hit["subtitle"] == "Тело и сон"


def test_signals_titles_follow_language_and_unrelated_queries_miss(client, data):
    assert hits(client, "шаги", "en")[1]["signals"][0]["title"] == "Activity: steps and workouts"
    assert hits(client, "сон", "ru")[1]["signals"][0]["title"] == "Сон"
    for q in ("vitamin d", "креон", "визит", "checkup"):
        assert "signals" not in hits(client, q)[1]


@pytest.mark.parametrize("q", ["кал", "сер", "акт", "тел", "ste", "сонография", "сонограф"])
def test_short_or_unrelated_words_do_not_surface_signals_pages(client, data, q):
    assert "signals" not in hits(client, q, "ru")[1]


def test_signals_group_comes_after_organs_and_markers(client, data):
    body, _ = hits(client, "сердце", "ru")
    kinds = [g["kind"] for g in body["groups"]]
    assert "signals" in kinds
    assert all(kinds.index(k) < kinds.index("signals") for k in ("organ", "marker") if k in kinds)
