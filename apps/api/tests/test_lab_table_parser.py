from services.lab_table_parser import (
    parse_markdown_lab_table,
    parse_reference,
    parse_result,
)

BLOOD_MD = """| Test | Result | Reference Range | Interpretation |
| --- | --- | --- | --- |
| Pancreatic Lipase | 35.7 U/L | 16.0 – 60.0 | Normal |
| Alpha-Amylase | 119 U/L | 28.0 – 100.0 | Slightly elevated → mild pancreatic stress |
| Pancreatic Amylase | 34.4 U/L | 13.0 – 53.0 | Normal |
| Alkaline Phosphatase | 117 U/L | 40.0 – 130.0 | Normal |
"""


def test_result_value_and_unit():
    r = parse_result("35.7 U/L")
    assert (r.value, r.unit, r.result_text, r.comparator) == (35.7, "U/L", None, None)


def test_result_integer():
    assert parse_result("119 U/L").value == 119.0


def test_result_decimal_comma():
    r = parse_result("1,5 ng/mL")
    assert (r.value, r.unit) == (1.5, "ng/mL")


def test_result_comparator():
    r = parse_result("<0.5 mg/L")
    assert (r.value, r.comparator, r.unit) == (0.5, "<", "mg/L")


def test_result_non_numeric_kept_as_text():
    r = parse_result("negative")
    assert r.value is None and r.result_text == "negative"


def test_result_empty():
    r = parse_result("")
    assert (r.value, r.unit, r.result_text, r.comparator) == (None, None, None, None)


def test_reference_en_dash():
    assert parse_reference("16.0 – 60.0") == (16.0, 60.0)


def test_reference_hyphen():
    assert parse_reference("16-60") == (16.0, 60.0)


def test_reference_upper_only():
    assert parse_reference("< 5.0") == (None, 5.0)
    assert parse_reference("up to 100") == (None, 100.0)


def test_reference_empty():
    assert parse_reference("") == (None, None)


def test_parse_table_yields_four_rows():
    rows = parse_markdown_lab_table(BLOOD_MD)
    assert len(rows) == 4
    assert rows[1].name == "Alpha-Amylase" and rows[1].result == "119 U/L"
    assert rows[1].reference == "28.0 – 100.0"


def test_parse_table_russian_headers_and_no_table():
    ru = "| Показатель | Результат | Референс |\n| --- | --- | --- |\n| Ферритин | 28 нг/мл | 30 - 400 |\n"
    rows = parse_markdown_lab_table(ru)
    assert rows[0].name == "Ферритин" and rows[0].reference == "30 - 400"
    assert parse_markdown_lab_table("just some prose, no table") == []


def test_result_range_like_value_is_text_not_number():
    r = parse_result("25–30")
    assert r.value is None and r.result_text == "25–30" and r.unit is None


def test_reference_markdown_escaped_comparator():
    assert parse_reference(r"\<10") == (None, 10.0)
    assert parse_reference("–") == (None, None)


def test_parameter_header_and_qualitative_rows():
    md = "| Parameter | Result | Normal Range | Notes |\n| --- | --- | --- | --- |\n| Leukocytes | 25–30 | \\<10 | Elevated |\n| Mucus | + | – | Present |\n"
    rows = parse_markdown_lab_table(md)
    assert [r.name for r in rows] == ["Leukocytes", "Mucus"]
    assert parse_result(rows[1].result).result_text == "+"


def test_units_column_is_captured():
    md = "| Test | Result | Units | Reference |\n| --- | --- | --- | --- |\n| Vitamin D | 24 | nmol/L | 75-250 |\n"
    rows = parse_markdown_lab_table(md)
    assert rows[0].unit == "nmol/L" and rows[0].result == "24"
