import datetime as dt

import pytest
from sqlmodel import select

from config import settings
from db.models import Biomarker, LabReport, Profile
from importers.refill_ranges import refill_ranges
from services import clock
from services.lab_text_parser import parse_lab_text
from services.range_candidates import RangeCandidate, extract_candidates
from tests.pdf_factory import text_pdf

TODAY = dt.date(2026, 11, 11)
HEADER = "Показатель Результат Норма Ед.Измер.\nДата 2025-12-20\n"
SEX_LINE = "HGB Гемоглобин 142 М.  130-160        Ж.  120-140 г/л"
AGE_LINE = "Тироксин свободный 15,2 до 60 лет 10.0 - 25.0 пмоль/л старше 60 лет 10.0 - 21.0 пмоль/л"
PDF_SEX_LINE = "Hemoglobin 142 M. 130-160 F. 120-140 g/L"
ADULT_LINE = "Тиреотропный гормон 3,1 взрослые 2,5 -5,8 мМЕ/л"
BOTH_LINE = "Ферритин 20 Женщины старше 30 лет 10 - 120 Мужчины старше 30 лет 30 - 300 нг/мл"


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda zone=None: TODAY)


def _profile(session, sex=None, birth=None):
    session.add(Profile(id=1, sex=sex, birth_date=birth))
    session.commit()


def _row(text, session=None):
    parsed = parse_lab_text(HEADER + text, session)
    assert parsed is not None
    return parsed.rows[0]


def test_extracts_sex_age_and_adult_candidates_from_real_shaped_lines():
    assert extract_candidates("М.  130-160        Ж.  120-140 г/л") == [
        RangeCandidate(130, 160, sex="male"), RangeCandidate(120, 140, sex="female")]
    assert extract_candidates("до 60 лет 10.0 - 25.0 пмоль/л старше 60 лет 10.0 - 21.0 пмоль/л") == [
        RangeCandidate(10.0, 25.0, age_max=59), RangeCandidate(10.0, 21.0, age_min=60)]
    assert extract_candidates("взрослые 2,5 -5,8") == [RangeCandidate(2.5, 5.8, age_min=18)]
    assert extract_candidates("Женщины старше 30 лет 10 - 120 Мужчины старше 30 лет 30 - 300") == [
        RangeCandidate(10, 120, sex="female", age_min=30), RangeCandidate(30, 300, sex="male", age_min=30)]
    assert extract_candidates("от 18 до 60 лет 3-7 дети 1-2 male 4-5 F 6-8") == [
        RangeCandidate(3, 7, age_min=18, age_max=60), RangeCandidate(1, 2, age_max=17),
        RangeCandidate(4, 5, sex="male"), RangeCandidate(6, 8, sex="female")]


def test_a_qualifier_without_a_number_range_is_ignored():
    assert extract_candidates("старше 60 лет") == [] and extract_candidates("4.0 - 9.0") == []


def test_without_a_profile_the_range_stays_blank_and_says_what_is_missing():
    row = _row(SEX_LINE)  # no session at all: no profile
    assert (row.ref_min, row.ref_max, row.needs_profile) == (None, None, "sex")


def test_sex_decides_the_range(session):
    _profile(session, sex="female")
    row = _row(SEX_LINE, session)
    assert (row.ref_min, row.ref_max, row.needs_profile, row.unit) == (120, 140, None, "g/L")
    assert row.is_out_of_range is True
    session.get(Profile, 1).sex = "male"
    session.commit()
    row = _row(SEX_LINE, session)
    assert (row.ref_min, row.ref_max, row.is_out_of_range) == (130, 160, False)


def test_age_decides_the_range(session):
    _profile(session, birth=dt.date(1990, 1, 1))  # 36
    assert (_row(AGE_LINE, session).ref_min, _row(AGE_LINE, session).ref_max) == (10.0, 25.0)
    session.get(Profile, 1).birth_date = dt.date(1960, 1, 1)  # 66
    session.commit()
    row = _row(AGE_LINE, session)
    assert (row.ref_min, row.ref_max, row.is_out_of_range, row.unit) == (10.0, 21.0, False, "pmol/L")


def test_adult_only_range(session):
    _profile(session, birth=dt.date(1990, 1, 1))
    assert (_row(ADULT_LINE, session).ref_min, _row(ADULT_LINE, session).ref_max) == (2.5, 5.8)
    session.get(Profile, 1).birth_date = dt.date(2015, 1, 1)
    session.commit()
    row = _row(ADULT_LINE, session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (None, None, None)  # a child: no candidate fits


def test_sex_and_age_together(session):
    _profile(session, sex="female", birth=dt.date(1990, 1, 1))
    assert (_row(BOTH_LINE, session).ref_min, _row(BOTH_LINE, session).ref_max) == (10, 120)


@pytest.mark.parametrize("sex,birth,line,needs", [
    (None, dt.date(1990, 1, 1), SEX_LINE, "sex"),
    ("male", None, AGE_LINE, "age"),
    (None, None, BOTH_LINE, "both"),
    ("female", None, BOTH_LINE, "age"),
    (None, dt.date(1990, 1, 1), BOTH_LINE, "sex"),
    ("male", None, ADULT_LINE, "age"),
])
def test_needs_profile_flags(session, sex, birth, line, needs):
    _profile(session, sex=sex, birth=birth)
    row = _row(line, session)
    assert (row.ref_min, row.ref_max) == (None, None) and row.needs_profile == needs


def test_ambiguous_candidates_stay_blank(session):
    _profile(session, sex="male", birth=dt.date(1990, 1, 1))
    row = _row("Тестостерон 15 М. 10-20 М. 12-25 нмоль/л", session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (None, None, None)
    # identical duplicates are not ambiguous
    assert _row("Тестостерон 15 М. 10-20 муж. 10-20 нмоль/л", session).ref_min == 10


def test_a_plain_range_is_untouched_and_never_asks_for_a_profile(session):
    row = _row("Лейкоциты  Процент 5,62 4-9", session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (4, 9, None)


def test_wrapped_qualified_range_lines_attach_to_the_row(session):
    _profile(session, sex="female")
    row = _row("HGB Гемоглобин 142\nМ.  130-160\nЖ.  120-140", session)
    assert (row.ref_min, row.ref_max) == (120, 140)


def test_needs_profile_is_in_the_upload_payload(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    pdf = text_pdf("Results Reference Unit", "Date 2025-12-20", PDF_SEX_LINE)
    r = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["needs_profile"] == "sex" and row["ref_min"] is None


def _stored_report(session, tmp_path, *lines, hash_="abc"):
    (tmp_path / "pdf").mkdir(exist_ok=True)
    (tmp_path / "pdf" / f"{hash_}.pdf").write_bytes(text_pdf("Results Reference Unit", "Date 2025-12-20", *lines))
    report = LabReport(test_date=dt.date(2025, 12, 20), source="pdf", file_hash=hash_)
    session.add(report)
    session.flush()
    return report


def test_refill_fills_only_blank_ranges_and_is_rerunnable(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, sex="female")
    report = _stored_report(session, tmp_path, PDF_SEX_LINE, "Leukocytes 5.62 4-9")
    session.add(Biomarker(report_id=report.id, marker_key="hemoglobin", display_name="Hemoglobin", raw_name="Hemoglobin", value=142, unit="g/L", needs_profile="sex"))
    session.add(Biomarker(report_id=report.id, marker_key="wbc", display_name="WBC", raw_name="Leukocytes", value=5.62, ref_min=1, ref_max=2, is_out_of_range=True))
    session.commit()
    assert refill_ranges(session) == 1
    hgb, wbc = session.exec(select(Biomarker).order_by(Biomarker.id)).all()
    assert (hgb.ref_min, hgb.ref_max, hgb.is_out_of_range) == (120, 140, True)
    assert (wbc.ref_min, wbc.ref_max) == (1, 2)  # never overwritten
    assert refill_ranges(session) == 0


def test_refill_leaves_ranges_blank_without_a_profile_and_skips_non_pdf(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    report = _stored_report(session, tmp_path, PDF_SEX_LINE)
    session.add(Biomarker(report_id=report.id, marker_key="hemoglobin", display_name="H", raw_name="Hemoglobin", value=142, unit="g/L", needs_profile="sex"))
    session.add(LabReport(test_date=TODAY, source="manual"))
    session.commit()
    assert refill_ranges(session) == 0
    assert session.exec(select(Biomarker)).one().ref_min is None
    _profile(session, sex="male")
    assert refill_ranges(session) == 1 and session.exec(select(Biomarker)).one().ref_max == 160


# ---- review fixes: undecidable lines, report-date age, colon qualifiers, mixed plain + qualified ----

@pytest.mark.parametrize("text", [
    "120-140 жен. 130-160 муж.",  # C1: the ranges come BEFORE their qualifiers
    "Женщины в менопаузе 50-100, Женщины 10-30",  # C2: unknown qualifier words
    "Беременные 11-15 Женщины 12-15",
    "Ж. (фолликулярная фаза) 2.4-12.6 Ж. (лютеиновая фаза) 1.0-9.0 М. 1.7-8.6",
    "Ж. 10-20 М.",  # a qualifier with no range after it
])
def test_undecidable_lines_give_no_candidates_and_a_blank_range(session, text):
    assert extract_candidates(text) == []
    _profile(session, sex="female", birth=dt.date(1966, 1, 1))
    row = _row(f"Эстрадиол 20 {text} пг/мл", session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (None, None, None)


def test_a_range_after_an_unrecognised_word_is_refused_on_its_own_too(session):
    _profile(session, sex="female")
    row = _row("Эстрадиол 20 Беременные 11-15 пг/мл", session)
    assert (row.ref_min, row.ref_max) == (None, None)


def test_report_date_decides_the_age_not_today(session):
    _profile(session, birth=dt.date(1965, 6, 1))  # 58 on 2023-12-20, 61 today
    text = "Тироксин свободный 15,2 до 60 лет 10-25 пмоль/л старше 60 лет 10-21 пмоль/л"
    parsed = parse_lab_text("Показатель Результат Норма Ед.Измер.\nДата 2023-12-20\n" + text, session)
    assert (parsed.rows[0].ref_min, parsed.rows[0].ref_max) == (10, 25)
    parsed = parse_lab_text("Показатель Результат Норма Ед.Измер.\n" + text, session)  # undated: today
    assert (parsed.rows[0].ref_min, parsed.rows[0].ref_max) == (10, 21)


def test_colon_after_sex_letters_and_words():
    assert extract_candidates("Ж: 12-150, М: 30-400") == [RangeCandidate(12, 150, sex="female"), RangeCandidate(30, 400, sex="male")]
    assert extract_candidates("муж: 1-2 жен: 3-4") == [RangeCandidate(1, 2, sex="male"), RangeCandidate(3, 4, sex="female")]


def test_a_plain_range_beside_a_qualified_one():
    line = "3.9-6.1, старше 60 лет 4.6-6.4"
    assert extract_candidates(line) == [RangeCandidate(3.9, 6.1), RangeCandidate(4.6, 6.4, age_min=60)]


def test_mixed_plain_and_qualified_decided_by_age(session):
    line = "Глюкоза 5 3.9-6.1, старше 60 лет 4.6-6.4 ммоль/л"
    _profile(session, birth=dt.date(1986, 1, 1))
    row = _row(line, session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (3.9, 6.1, None)
    _profile_clear = session.get(Profile, 1)
    _profile_clear.birth_date = None
    session.commit()
    row = _row(line, session)
    assert (row.ref_min, row.ref_max, row.needs_profile) == (None, None, "age")


# ---- stored needs_profile, safe refill, the refill endpoint ----

def _hgb(report, **over):
    return Biomarker(**{"report_id": report.id, "marker_key": "hemoglobin", "display_name": "Hemoglobin",
                        "raw_name": "Hemoglobin", "value": 142, "unit": "g/L", **over})


def test_a_cleared_range_stays_cleared(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, sex="female")
    report = _stored_report(session, tmp_path, PDF_SEX_LINE)
    session.add(_hgb(report))  # blank, but not because the profile was missing: the owner cleared it
    session.commit()
    assert refill_ranges(session) == 0
    assert session.exec(select(Biomarker)).one().ref_min is None


def test_refill_clears_needs_profile_when_it_fills(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, sex="female")
    report = _stored_report(session, tmp_path, PDF_SEX_LINE)
    session.add(_hgb(report, needs_profile="sex"))
    session.commit()
    assert refill_ranges(session) == 1
    assert session.exec(select(Biomarker)).one().needs_profile is None


def test_refill_skips_rows_whose_key_repeats_in_the_report(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, sex="female")
    report = _stored_report(session, tmp_path, PDF_SEX_LINE, "Hemoglobin 142 M. 100-110 F. 90-95 g/L")
    session.add(_hgb(report, needs_profile="sex"))
    session.add(_hgb(report, needs_profile="sex"))
    session.commit()
    assert refill_ranges(session) == 0


def test_refill_matches_by_unit_too(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, sex="female")
    report = _stored_report(session, tmp_path, PDF_SEX_LINE, "Hemoglobin 142 M. 13-16 F. 12-14 g/dL")
    session.add(_hgb(report, needs_profile="sex", unit="g/dL"))
    session.commit()
    assert refill_ranges(session) == 1
    assert (session.exec(select(Biomarker)).one().ref_max) == 14


def test_refill_uses_the_age_on_the_report_date(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _profile(session, birth=dt.date(1965, 6, 1))
    (tmp_path / "pdf").mkdir(exist_ok=True)
    (tmp_path / "pdf" / "old.pdf").write_bytes(text_pdf("Results Reference Unit", "Date 2023-12-20",
        "Free T4 15.2 under 60 years 10-25 pmol/L over 60 years 10-21 pmol/L"))
    report = LabReport(test_date=dt.date(2023, 12, 20), source="pdf", file_hash="old")
    session.add(report)
    session.flush()
    session.add(Biomarker(report_id=report.id, marker_key="t4", display_name="T4", raw_name="Free T4", value=15.2, unit="pmol/L", needs_profile="age"))
    session.commit()
    assert refill_ranges(session) == 1
    assert session.exec(select(Biomarker)).one().ref_max == 25


def _confirm_body(file_hash, rows):
    return {"test_date": "2025-12-20", "lab_name": "L", "file_hash": file_hash, "rows": rows}


def test_saved_biomarkers_keep_needs_profile_and_the_list_shows_it(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    pdf = text_pdf("Results Reference Unit", "Date 2025-12-20", PDF_SEX_LINE)
    up = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf, "application/pdf")})
    row = up.json()["rows"][0]
    assert client.post("/api/v1/labs/confirm", json=_confirm_body(up.json()["file_hash"], [row])).status_code == 201
    item = next(i for i in client.get("/api/v1/biomarkers").json() if i["marker_key"] == "hemoglobin")
    assert item["needs_profile"] == "sex" and item["ref_min"] is None


def test_confirm_without_needs_profile_rederives_it_from_the_stored_pdf(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    pdf = text_pdf("Results Reference Unit", "Date 2025-12-20", PDF_SEX_LINE)
    up = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf, "application/pdf")})
    row = {k: v for k, v in up.json()["rows"][0].items() if k in ("name", "value", "unit", "ref_min", "ref_max")}
    assert client.post("/api/v1/labs/confirm", json=_confirm_body(up.json()["file_hash"], [row])).status_code == 201
    item = next(i for i in client.get("/api/v1/biomarkers").json() if i["marker_key"] == "hemoglobin")
    assert item["needs_profile"] == "sex"


def test_a_row_with_a_range_never_reports_needs_profile(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    body = {"test_date": "2025-12-20", "lab_name": "L", "rows": [{"name": "Hemoglobin", "value": 142, "unit": "g/L", "ref_min": 120, "ref_max": 160, "needs_profile": "sex"}]}
    assert client.post("/api/v1/labs/manual", json=body).status_code == 201
    item = next(i for i in client.get("/api/v1/biomarkers").json() if i["marker_key"] == "hemoglobin")
    assert item["needs_profile"] is None


def test_refill_endpoint_fills_from_the_current_profile(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    pdf = text_pdf("Results Reference Unit", "Date 2025-12-20", PDF_SEX_LINE)
    up = client.post("/api/v1/labs/upload", files={"file": ("a.pdf", pdf, "application/pdf")})
    client.post("/api/v1/labs/confirm", json=_confirm_body(up.json()["file_hash"], [up.json()["rows"][0]]))
    empty = client.post("/api/v1/profile/refill-ranges", headers={"Accept-Language": "ru"})
    assert empty.status_code == 422 and "профиле" in empty.json()["detail"]
    client.put("/api/v1/profile", json={"sex": "female"})
    assert client.post("/api/v1/profile/refill-ranges").json() == {"filled": 1}
    item = next(i for i in client.get("/api/v1/biomarkers").json() if i["marker_key"] == "hemoglobin")
    assert (item["ref_min"], item["ref_max"], item["needs_profile"]) == (120, 140, None)
    assert client.post("/api/v1/profile/refill-ranges").json() == {"filled": 0}


def test_the_migration_matches_the_models(tmp_path):
    import os
    import subprocess
    import sys
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'scratch.db'}"}
    for command in (["upgrade", "head"], ["check"]):
        done = subprocess.run([sys.executable, "-m", "alembic", *command], env=env, cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
