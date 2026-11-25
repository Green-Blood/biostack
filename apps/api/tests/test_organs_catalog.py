import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import MedicalRecord, ScanMeasurement
from services.organs import ORGANS, get_param, organ_name, organs_in, param_name


def test_every_organ_has_a_headline_param_and_side():
    for organ in ORGANS.values():
        key, side = organ.headline
        param = get_param(organ.key, key)
        assert param is not None, organ.key
        if param.sides:
            assert side in ("left", "right")
        else:
            assert side == ""


def test_organs_in_kidneys_genitive_plural():
    assert organs_in("УЗИ почек") == ["kidneys"]


def test_organs_in_finds_ru_and_en_in_order():
    assert organs_in("УЗИ щитовидной железы; Kidneys, liver") == ["thyroid", "kidneys", "liver"]


def test_names_exist_in_both_languages():
    for lang in ("en", "ru"):
        for organ in ORGANS.values():
            assert organ_name(organ.key, lang) not in ("", organ.key)
            for p in organ.params:
                assert param_name(p.key, lang) not in ("", p.key)


def test_get_param_unknown_is_none():
    assert get_param("thyroid", "nope") is None
    assert get_param("nope", "volume_total") is None


def _record(session):
    rec = MedicalRecord(record_type="imaging", title="x", record_date=dt.date(2024, 1, 1))
    session.add(rec)
    session.commit()
    return rec


def test_models_roundtrip_and_unique(session):
    rec = _record(session)
    session.add(ScanMeasurement(record_id=rec.id, organ_key="kidneys", param_key="length_cm", side="left", value=10.5))
    session.add(ScanMeasurement(record_id=rec.id, organ_key="kidneys", param_key="length_cm", side="right", value=11.0))
    session.commit()
    for _ in range(2):
        session.add(ScanMeasurement(record_id=rec.id, organ_key="spleen", param_key="length_cm", value=9.0))
    with pytest.raises(IntegrityError):
        session.commit()
