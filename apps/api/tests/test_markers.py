from db.models import MarkerAlias
from services.markers import canonical_unit, normalize_marker, units_compatible


def test_english_and_russian_names_map_to_same_key():
    for raw in ("Alpha-Amylase", "альфа-амилаза", " ALPHA AMYLASE ", "Амилаза альфа"):
        m = normalize_marker(raw)
        assert m is not None and m.marker_key == "alpha_amylase", raw


def test_other_known_markers():
    assert normalize_marker("Pancreatic Lipase").marker_key == "pancreatic_lipase"
    assert normalize_marker("Витамин D (25-OH)").marker_key == "vitamin_d_25_oh"
    assert normalize_marker("Ферритин").marker_key == "ferritin"
    assert normalize_marker("Testosterone, total").marker_key == "testosterone_total"


def test_unknown_marker_returns_none():
    assert normalize_marker("Totally Unknown Thing") is None


def test_db_alias_is_used_as_fallback(session):
    session.add(MarkerAlias(raw_name="Мой маркер", marker_key="my_marker", display_name="My marker"))
    session.commit()
    m = normalize_marker("мой маркер", session)
    assert m is not None and m.marker_key == "my_marker"


def test_unit_canonicalization_and_compatibility():
    assert canonical_unit("ferritin", "нг/мл") == "ng/mL"
    assert canonical_unit("ferritin", "ng/ml") == "ng/mL"
    assert units_compatible("ng/mL", "нг/мл") is True
    assert units_compatible("ng/mL", "nmol/L") is False
    assert canonical_unit("x", "weird/unit") == "weird/unit"


def test_every_catalog_entry_has_a_valid_system_and_retest_interval():
    import json
    from pathlib import Path

    from services.markers import MARKER_SYSTEMS

    entries = json.loads((Path(__file__).parent.parent / "services" / "marker_aliases.json").read_text(encoding="utf-8"))
    for e in entries:
        assert e.get("system") in MARKER_SYSTEMS, e["marker_key"]
        assert isinstance(e.get("retest_days"), int) and e["retest_days"] > 0, e["marker_key"]


def test_system_and_retest_helpers():
    from services.markers import marker_retest_days, marker_system

    assert marker_system("vitamin_d_25_oh") == "vitamins" and marker_retest_days("vitamin_d_25_oh") == 90
    assert marker_system("tsh") == "thyroid"
    assert marker_system("unmapped:foo") == "other" and marker_retest_days("unmapped:foo") is None
