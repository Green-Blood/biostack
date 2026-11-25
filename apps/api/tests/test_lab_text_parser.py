import datetime as dt

from services.lab_text_parser import parse_lab_text

REPORT = """SAMPLE LAB
Ф.И.О. Тестов Тест Тестович
РЕЗУЛЬТАТЫ
АНАЛИЗОВДата рождения 01.01.1990
Дата 2025-12-20(Центр)
Телефоны: +998 71 207-50-45, +998 71
массив Карасу 4 ул. Гулсанам,  дом-2.
 Показатель Результат Норма Ед.Измер.
Лейкоциты  Процент 5,62 4-9
RDW-CV ( Анизоцитоз эритроцитов) 11 11.5-14.5 %
HGB Гемоглобин 142 М.  130-160        Ж.  120-140 г/л
PLT Тромбоциты 227 218-362 10
9
/л
Тиреотропный гормон (ТТГ) 5,0 0,3-4,0 мME/л
Фолиевая кислота 6,9 3,2- 19,6 ng/ml
Total Vitamin D - 25 OH (Витамин Д
общий) 27,6
дефицитное состояние: < 10 ng/ml
недостаточность: 10 - < 29 ng/ml
нормальное состояние: 30 - 100 ng/ml
потенциальная токсичность: > 100
ng/ml
Страница 2
"""


def _rows():
    parsed = parse_lab_text(REPORT)
    assert parsed is not None
    return parsed, {r.name: r for r in parsed.rows}


def test_reads_the_date_but_not_the_birth_date():
    parsed, _ = _rows()
    assert parsed.test_date == dt.date(2025, 12, 20)


def test_reads_value_reference_and_unit_from_a_plain_row():
    _, rows = _rows()
    row = rows["Тиреотропный гормон (ТТГ)"]
    assert (row.value, row.ref_min, row.ref_max, row.unit) == (5.0, 0.3, 4.0, "мME/л")
    assert row.is_out_of_range is True


def test_a_name_wrapped_over_two_lines_is_joined_and_mapped_to_vitamin_d():
    _, rows = _rows()
    row = next(r for r in rows.values() if r.value == 27.6)
    assert row.marker_key == "vitamin_d_25_oh" and row.name.startswith("Total Vitamin D")


def test_the_normal_state_line_under_a_value_supplies_its_range_and_unit():
    _, rows = _rows()
    row = next(r for r in rows.values() if r.value == 27.6)
    assert (row.ref_min, row.ref_max) == (30.0, 100.0) and row.unit == "ng/mL" and row.is_out_of_range is True


def test_sex_specific_ranges_are_left_blank_rather_than_guessed():
    _, rows = _rows()
    row = rows["HGB Гемоглобин"]
    assert row.value == 142 and row.ref_min is None and row.ref_max is None and row.unit == "g/L"


def test_a_stray_digit_unit_is_not_taken_as_a_unit():
    _, rows = _rows()
    assert rows["PLT Тромбоциты"].unit in (None, "")


def test_address_phone_and_page_lines_are_not_results():
    parsed, rows = _rows()
    names = " ".join(rows)
    assert not any(word in names for word in ("Телефоны", "массив", "Страница", "Дата"))
    assert len(parsed.rows) == 7


def test_a_single_test_report_with_a_timestamped_value_line():
    text = ("Дата 20.12.2025(Центр)\nНаименование Анализа Результат Норма Ед.изм\nЙод в сыворотке\n"
            "2025-12-25 15:24:05 95.5\nнедостаточность до 100,0\nнорма от 100,0 до 200,0\n")
    parsed = parse_lab_text(text)
    row = parsed.rows[0]
    assert row.name == "Йод в сыворотке" and row.value == 95.5
    assert (row.ref_min, row.ref_max) == (100.0, 200.0) and row.is_out_of_range is True


def test_text_without_any_recognisable_result_is_not_a_lab_report():
    assert parse_lab_text("Просто письмо врача без цифр") is None
    assert parse_lab_text("") is None


def test_a_clinical_note_with_numbers_but_no_results_table_is_not_a_lab_report():
    note = "Заключение УЗИ\nПечень увеличена, размеры правой доли 150 мм\nЖелчный пузырь 80 - 90 мм\n"
    assert parse_lab_text(note) is None


def test_age_band_and_toxicity_fragments_are_not_results():
    text = ("Показатель Результат Норма\\nГлюкоза 5,1 3,3-5,6 ммоль/л\\n30 Женщины старше 55 лет 12\\n"
            "токчиность выше 100\\nпотенциальная токсичность выше 100\\nОбщий анализ крови 1\\n").replace("\\n", "\n")
    parsed = parse_lab_text(text)
    assert [r.name for r in parsed.rows] == ["Глюкоза"]


def test_interpretation_lines_become_the_four_printed_tiers():
    _, rows = _rows()
    row = next(r for r in rows.values() if r.value == 27.6)
    got = [(t.tier, t.min, t.max) for t in row.tiers]
    assert got == [("deficient", None, 10.0), ("insufficient", 10.0, 29.0),
                   ("normal", 30.0, 100.0), ("toxic", 100.0, None)]
    assert row.tiers[0].label == "дефицитное состояние" and row.tiers[3].label == "потенциальная токсичность"


def test_rows_without_interpretation_lines_have_no_tiers():
    _, rows = _rows()
    assert rows["Тиреотропный гормон (ТТГ)"].tiers == []


def test_tier_words_map_to_tiers():
    from services.lab_text_parser import parse_tier_line

    assert parse_tier_line("повышенное содержание: > 50 ng/ml").tier == "high"
    assert parse_tier_line("избыток: 5 - 9").tier == "high"
    assert parse_tier_line("Норма: 0,3 - 4,0 мМЕ/л").tier == "normal"
    assert parse_tier_line("Тиреотропный гормон 5,0 0,3-4,0") is None


def test_a_lone_normal_line_is_not_a_tier_set():
    parsed = parse_lab_text("РЕЗУЛЬТАТЫ\nНорма Ед\nФерритин 50 \nнормальное состояние: 30 - 100 ng/ml\n")
    assert parsed is not None and parsed.rows[0].tiers == [] and parsed.rows[0].ref_max == 100.0


def test_a_unit_with_a_superscript_power_of_ten_is_kept_whole():
    text = "Показатель Результат Норма Ед.Измер.\nRBC Эритроциты 5,1 4.0-5.0 10¹²/л\nWBC Лейкоциты 6,2 4-9 10⁹/л\n"
    rows = {r.name: r for r in parse_lab_text(text).rows}
    assert rows["RBC Эритроциты"].unit == "10^12/L" and rows["WBC Лейкоциты"].unit == "10^9/L"
