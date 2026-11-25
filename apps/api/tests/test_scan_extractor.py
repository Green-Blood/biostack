"""Rule-based extraction of organ measurements from ultrasound report text. All values are synthetic."""
import pytest

from services.organs import get_param
from services.scan_extractor import Extraction, Measurement, extract_rule


def _vals(ex: Extraction) -> dict[tuple[str, str, str], float | str | None]:
    return {(m.organ_key, m.param_key, m.side): (m.value if m.value is not None else m.value_text)
            for m in ex.measurements}


def _assert_valid(ex: Extraction) -> None:
    keys = [(m.organ_key, m.param_key, m.side) for m in ex.measurements]
    assert len(keys) == len(set(keys))
    for m in ex.measurements:
        param = get_param(m.organ_key, m.param_key)
        assert param is not None, m
        assert m.unit == param.unit
        assert (m.side in ("left", "right")) if param.sides else m.side == ""
        if param.kind == "numeric":
            assert m.value is not None and m.value_text is None
        else:
            assert m.value is None and m.value_text


THYROID_EN = """Thyroid gland ultrasound findings:
• Right lobe: 12×15×44 mm (5.2 cm³)
• Left lobe: 13×16×40 mm (5.0 cm³)
• Detected hyperechoic nodule 11×9 mm with small calcifications (TI-RADS 4)
• Echogenicity increased (diffuse changes)
• Total volume: 10.2 cm³ (within normal range for male 57 kg)"""


def test_thyroid_flat_report_uses_title_organ():
    ex = extract_rule("Thyroid Ultrasound", THYROID_EN)
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("thyroid", "volume_total", "")] == pytest.approx(10.2)
    assert v[("thyroid", "volume_lobe", "right")] == pytest.approx(5.2)
    assert v[("thyroid", "volume_lobe", "left")] == pytest.approx(5.0)
    assert v[("thyroid", "length_mm", "right")] == pytest.approx(44)
    assert v[("thyroid", "length_mm", "left")] == pytest.approx(40)
    assert v[("thyroid", "width_mm", "right")] == pytest.approx(12)
    assert v[("thyroid", "width_mm", "left")] == pytest.approx(13)
    assert v[("thyroid", "thickness_mm", "right")] == pytest.approx(15)
    assert v[("thyroid", "thickness_mm", "left")] == pytest.approx(16)
    assert v[("thyroid", "nodule_max_mm", "")] == pytest.approx(11)
    assert ("thyroid", "nodule_count", "") not in v  # the report prints no count
    assert v[("thyroid", "tirads", "")] == 4
    assert v[("thyroid", "echogenicity", "")] == "increased"
    assert ex.organs == ["thyroid"]


def test_prostate_ignores_normal_range_text():
    text = ("Bladder: volume 250 ml, wall thickness 3 mm, residual urine 5 ml (normal)"
            "Prostate: 17 cm³ (normal range 25–45 mm dimensions)")
    ex = extract_rule("Ultrasound of Prostate & Bladder", text)
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("bladder", "volume_ml", "")] == pytest.approx(250)
    assert v[("bladder", "wall_thickness_mm", "")] == pytest.approx(3)
    assert v[("bladder", "residual_urine_ml", "")] == pytest.approx(5)
    assert v[("prostate", "volume_cm3", "")] == pytest.approx(17)
    for p in ("length_mm", "width_mm", "thickness_mm"):
        assert ("prostate", p, "") not in v
    assert set(ex.organs) == {"prostate", "bladder"}


ABDOMINAL = """Abdominal ultrasound
• Liver:
  ◦ Right lobe: 12.9 cm, Left: 6.0 cm
• Gallbladder:
  ◦ Size: 6.0 × 2.6 cm
  ◦ Wall: 2 mm, multiple echogenic inclusions (1–2 mm, 5–6 units) — biliary sludge
• Pancreas:
  ◦ Head 1.8 cm, Body 1.5 cm, Tail 1.8 cm (normal)
• Spleen: 9.0 cm (normal)
• Kidneys: Normal position and structure"""


def test_abdominal_sections():
    ex = extract_rule("Abdominal Ultrasound", ABDOMINAL)
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("liver", "lobe_size_cm", "right")] == pytest.approx(12.9)
    assert v[("liver", "lobe_size_cm", "left")] == pytest.approx(6.0)
    assert v[("gallbladder", "length_cm", "")] == pytest.approx(6.0)
    assert v[("gallbladder", "width_cm", "")] == pytest.approx(2.6)
    assert v[("gallbladder", "wall_thickness_mm", "")] == pytest.approx(2)
    assert [k for k in v if k[0] == "gallbladder"] == [
        ("gallbladder", "length_cm", ""), ("gallbladder", "width_cm", ""), ("gallbladder", "wall_thickness_mm", "")]
    assert v[("pancreas", "head_cm", "")] == pytest.approx(1.8)
    assert v[("pancreas", "body_cm", "")] == pytest.approx(1.5)
    assert v[("pancreas", "tail_cm", "")] == pytest.approx(1.8)
    assert v[("spleen", "length_cm", "")] == pytest.approx(9.0)
    assert "kidneys" in ex.organs
    assert not [m for m in ex.measurements if m.organ_key == "kidneys"]


def test_kidney_sides_with_cyrillic_x_and_comma():
    text = "Kidneys:\n• Right kidney — 9,8х4,5 cm; left — 10,0×4,5 cm"
    ex = extract_rule("Kidney ultrasound", text)
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("kidneys", "length_cm", "right")] == pytest.approx(9.8)
    assert v[("kidneys", "length_cm", "left")] == pytest.approx(10.0)
    assert v[("kidneys", "width_cm", "right")] == pytest.approx(4.5)
    assert v[("kidneys", "width_cm", "left")] == pytest.approx(4.5)


def test_russian_thyroid():
    text = ("Правая доля 12×15×44 мм, объём 5,2 мл. Левая доля 13×16×40 мм, объём 5,0 мл. "
            "Эхогенность повышена. Общий объём 10,2 мл")
    ex = extract_rule("УЗИ щитовидной железы", text)
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("thyroid", "volume_total", "")] == pytest.approx(10.2)
    assert v[("thyroid", "volume_lobe", "right")] == pytest.approx(5.2)
    assert v[("thyroid", "volume_lobe", "left")] == pytest.approx(5.0)
    assert v[("thyroid", "length_mm", "right")] == pytest.approx(44)
    assert v[("thyroid", "length_mm", "left")] == pytest.approx(40)
    assert v[("thyroid", "width_mm", "right")] == pytest.approx(12)
    assert v[("thyroid", "width_mm", "left")] == pytest.approx(13)
    assert v[("thyroid", "thickness_mm", "right")] == pytest.approx(15)
    assert v[("thyroid", "thickness_mm", "left")] == pytest.approx(16)
    assert v[("thyroid", "echogenicity", "")] == "повышена"
    assert ex.organs == ["thyroid"]


def test_first_value_wins_and_unreadable_gives_nothing():
    ex = extract_rule("Thyroid Ultrasound", "Total volume: 10.2 cm³\nTotal volume: 12.0 cm³")
    assert _vals(ex)[("thyroid", "volume_total", "")] == pytest.approx(10.2)
    assert len(ex.measurements) == 1
    assert extract_rule("Ultrasound", "Все в норме, без патологии.") == Extraction(organs=[], measurements=[])


def test_cm_converted_to_mm_and_title_with_several_organs_ignores_headerless_lines():
    ex = extract_rule("Thyroid Ultrasound", "Right lobe: 1.2×1.5×4.4 cm")
    v = _vals(ex)
    assert v[("thyroid", "length_mm", "right")] == pytest.approx(44)
    assert v[("thyroid", "width_mm", "right")] == pytest.approx(12)
    assert extract_rule("Ultrasound of Prostate & Bladder", "Volume 250 ml").measurements == []


def test_measurement_shape():
    m = Measurement("spleen", "length_cm", "", 9.0, None, "cm")
    assert m.value == 9.0 and m.unit == "cm"


# --- Fix round 1: single-length fallback is a positive allow-list; dropped parentheses end a clause ---

@pytest.mark.parametrize("title, text", [
    ("Abdominal Ultrasound", "Spleen: lesion 8 mm"),
    ("Abdominal Ultrasound", "Spleen: accessory spleen 12 mm"),
    ("Abdominal Ultrasound", "Kidneys:\nRight kidney: cyst 8 mm"),
    ("Abdominal Ultrasound", "Kidneys:\nRight kidney: stone 4 mm; left kidney: calculus 5 mm"),
    ("Abdominal Ultrasound", "Kidneys:\nRight: concretion 4 mm"),
    ("Abdominal Ultrasound", "Liver:\nRight lobe: cyst 12 mm"),
    ("Abdominal Ultrasound", "Liver:\nRight lobe: hemangioma 14 mm"),
    ("Abdominal Ultrasound", "Liver:\nLeft lobe: focal lesion 9 mm"),
    ("Abdominal Ultrasound", "Liver:\nPortal vein 11 mm"),
    ("Abdominal Ultrasound", "Kidneys:\nRight ureter 4 mm"),
    ("УЗИ брюшной полости", "Правая почка: киста 8 мм"),
    ("УЗИ брюшной полости", "Печень:\nПравая доля: образование 15 мм"),
])
def test_single_length_with_other_noun_is_not_organ_size(title, text):
    ex = extract_rule(title, text)
    assert [m for m in ex.measurements if m.param_key in ("length_cm", "lobe_size_cm")] == []


@pytest.mark.parametrize("title, text, key, value", [
    ("Abdominal Ultrasound", "Spleen: 9.0 cm", ("spleen", "length_cm", ""), 9.0),
    ("Abdominal Ultrasound", "Spleen: size 9.0 cm", ("spleen", "length_cm", ""), 9.0),
    ("Abdominal Ultrasound", "Liver:\nRight lobe: 12.9 cm", ("liver", "lobe_size_cm", "right"), 12.9),
    ("Abdominal Ultrasound", "Kidneys:\nRight kidney 9.8 cm", ("kidneys", "length_cm", "right"), 9.8),
    ("Abdominal Ultrasound", "Kidneys:\nLeft kidney length 10.1 cm", ("kidneys", "length_cm", "left"), 10.1),
    ("УЗИ брюшной полости", "Селезёнка: 9,0 см", ("spleen", "length_cm", ""), 9.0),
    ("УЗИ брюшной полости", "Селезёнка: размер 9,0 см", ("spleen", "length_cm", ""), 9.0),
])
def test_bare_single_length_is_organ_size(title, text, key, value):
    assert _vals(extract_rule(title, text))[key] == pytest.approx(value)


def test_dropped_parenthesis_ends_the_clause_for_side():
    ex = extract_rule("Thyroid Ultrasound", "Right lobe: 12×15×44 mm (normal) Left lobe 5.0 cm³")
    _assert_valid(ex)
    v = _vals(ex)
    assert v[("thyroid", "length_mm", "right")] == pytest.approx(44)
    assert v[("thyroid", "width_mm", "right")] == pytest.approx(12)
    assert v[("thyroid", "thickness_mm", "right")] == pytest.approx(15)
    assert v[("thyroid", "volume_lobe", "left")] == pytest.approx(5.0)
    assert {k for k in v if k[2] == "left"} == {("thyroid", "volume_lobe", "left")}


# --- Final fix wave: lesion sizes are not organ sizes; nodule_count only when printed; highest TI-RADS ---

@pytest.mark.parametrize("title, text, expected", [
    ("Kidney ultrasound", "Right kidney: cyst 12×10 mm in the upper pole. Size 105×48 mm.",
     {("kidneys", "length_cm", "right"): 10.5, ("kidneys", "width_cm", "right"): 4.8}),
    ("Abdominal Ultrasound", "Gallbladder: contains a stone 8×6 mm. Size 65×25 mm",
     {("gallbladder", "length_cm", ""): 6.5, ("gallbladder", "width_cm", ""): 2.5}),
    ("УЗИ почек", "Правая почка: киста 12×10 мм. Размеры 105×48 мм",
     {("kidneys", "length_cm", "right"): 10.5, ("kidneys", "width_cm", "right"): 4.8}),
    ("УЗИ брюшной полости", "Желчный пузырь: конкремент 8×6 мм. Размеры 65×25 мм",
     {("gallbladder", "length_cm", ""): 6.5, ("gallbladder", "width_cm", ""): 2.5}),
])
def test_lesion_dimensions_are_not_organ_size(title, text, expected):
    ex = extract_rule(title, text)
    _assert_valid(ex)
    v = _vals(ex)
    sizes = {k: val for k, val in v.items() if k[1] in ("length_cm", "width_cm")}
    assert sizes == pytest.approx(expected)


@pytest.mark.parametrize("text", [
    "Right kidney: cyst 12×10 mm",
    "Right kidney: polyp 12×10 mm",
    "Liver:\nRight lobe: hemangioma 14×12 mm",
    "Gallbladder: polyp 5×4 mm",
    "Spleen: focal lesion 12×10 mm",
    "Правая почка: конкремент 6×5 мм",
    "Правая почка: в верхнем полюсе киста, 12×10 мм",
    "Желчный пузырь: полип 5×4 мм",
    "Селезенка: очаговое образование 12×10 мм",
])
def test_lesion_only_gives_no_organ_size(text):
    ex = extract_rule("УЗИ брюшной полости", text)
    assert [m for m in ex.measurements if m.param_key in ("length_cm", "width_cm", "lobe_size_cm")] == []


def test_nodule_count_not_computed_from_repeated_dimensions():
    text = "Nodule 11×9 mm in right lobe. Conclusion: nodule of the right lobe 11×9 mm"
    v = _vals(extract_rule("Thyroid Ultrasound", text))
    assert ("thyroid", "nodule_count", "") not in v
    assert v[("thyroid", "nodule_max_mm", "")] == pytest.approx(11)


@pytest.mark.parametrize("text, count, largest", [
    ("2 nodules: 11×9 mm and 6×5 mm", 2, 11),
    ("Узлов: 3, наибольший 14×10 мм", 3, 14),
    ("2 узла: 11×9 мм и 6×5 мм", 2, 11),
])
def test_nodule_count_when_printed(text, count, largest):
    v = _vals(extract_rule("Thyroid Ultrasound", text))
    assert v[("thyroid", "nodule_count", "")] == count
    assert v[("thyroid", "nodule_max_mm", "")] == pytest.approx(largest)


@pytest.mark.parametrize("text", [
    "Nodule: 11×9 mm",
    "Nodule 1: 11×9 mm",
    "TI-RADS 4 nodule 11×9 mm",
    "Bethesda 4 nodule 6×5 mm",
    "Single nodule 7×5 mm",
    "One nodule 7×5 mm",
    "Один узел 6×5 мм, второй узел 4×3 мм",
    "Единичный узел 6×5 мм",
])
def test_nodule_numbers_are_not_a_count(text):
    assert ("thyroid", "nodule_count", "") not in _vals(extract_rule("Thyroid Ultrasound", text))


def test_highest_tirads_wins():
    text = "Nodule 6×5 mm in left lobe (TI-RADS 3).\nNodule 11×9 mm in right lobe, TI-RADS 4"
    assert _vals(extract_rule("Thyroid Ultrasound", text))[("thyroid", "tirads", "")] == 4
    text = "Nodule 11×9 mm, TI-RADS 4. Second nodule 6×5 mm, TI-RADS 3"
    assert _vals(extract_rule("Thyroid Ultrasound", text))[("thyroid", "tirads", "")] == 4


# --- Re-review: the header's side carries only while nothing later on the line names a side or re-names the organ ---

@pytest.mark.parametrize("text, expected", [
    ("Right kidney: 98×45 mm. Left kidney 100×46 mm. Parenchyma 14 mm.",
     {("kidneys", "length_cm", "right"): 9.8, ("kidneys", "width_cm", "right"): 4.5,
      ("kidneys", "length_cm", "left"): 10.0, ("kidneys", "width_cm", "left"): 4.6}),
    ("Правая почка: 98×45 мм. Левая почка 100×46 мм, ЧЛС не расширена. Паренхима 14 мм",
     {("kidneys", "length_cm", "right"): 9.8, ("kidneys", "width_cm", "right"): 4.5,
      ("kidneys", "length_cm", "left"): 10.0, ("kidneys", "width_cm", "left"): 4.6}),
    ("Left kidney: 100×46 mm. Right 98×45 mm. Parenchyma 15 mm",
     {("kidneys", "length_cm", "right"): 9.8, ("kidneys", "width_cm", "right"): 4.5,
      ("kidneys", "length_cm", "left"): 10.0, ("kidneys", "width_cm", "left"): 4.6}),
    ("Right kidney: absent. Single kidney 120×55 mm.", {}),
    ("Правая почка: удалена. Почка 120×55 мм, паренхима 16 мм", {}),
    ("Right kidney: cyst 12×10 mm in the upper pole. Size 105×48 mm.",
     {("kidneys", "length_cm", "right"): 10.5, ("kidneys", "width_cm", "right"): 4.8}),
    ("Right kidney: no stones. Size 105×48 mm",
     {("kidneys", "length_cm", "right"): 10.5, ("kidneys", "width_cm", "right"): 4.8}),
])
def test_header_side_carries_only_when_unambiguous(text, expected):
    ex = extract_rule("Kidney ultrasound", text)
    _assert_valid(ex)
    assert _vals(ex) == pytest.approx(expected)
