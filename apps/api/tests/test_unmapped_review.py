import datetime as dt

from sqlmodel import Session

from db.models import Biomarker, LabReport
from services.i18n_messages import EN, RU


def _unmapped(engine, rows):
    """rows: (date, raw_name, value, text, unit)."""
    with Session(engine) as s:
        for d, name, value, text, unit in rows:
            rep = LabReport(test_date=d)
            s.add(rep)
            s.flush()
            s.add(Biomarker(report_id=rep.id, marker_key="unmapped:" + name.lower(), display_name=name,
                            raw_name=name, value=value, result_text=text, unit=unit))
        s.commit()


RU_H = {"Accept-Language": "ru"}


def test_catalog_shape_sorted_and_localized(client):
    en = client.get("/api/v1/labs/marker-catalog").json()
    assert en and set(en[0]) == {"marker_key", "display_name", "system"}
    names = [m["display_name"].lower() for m in en]
    assert names == sorted(names)
    ru = client.get("/api/v1/labs/marker-catalog", headers=RU_H).json()
    assert len(ru) == len(en)
    assert [m["display_name"].lower() for m in ru] == sorted(m["display_name"].lower() for m in ru)
    by_key = {m["marker_key"]: m for m in ru}
    assert by_key["alpha_amylase"]["display_name"] == "Альфа-амилаза"
    assert {m["marker_key"]: m for m in en}["alpha_amylase"]["display_name"] == "Alpha-Amylase"


def test_unmapped_items_carry_latest_numeric(client, engine):
    _unmapped(engine, [(dt.date(2024, 1, 1), "Zinc x", 5.0, None, "mg"),
                       (dt.date(2024, 6, 1), "Zinc x", 7.5, None, "mg"),
                       (dt.date(2024, 7, 1), "Zinc x", None, "trace", ""),
                       (dt.date(2024, 3, 1), "Mucus", None, "+", "")])
    items = {i["raw_name"]: i for i in client.get("/api/v1/review/unmapped").json()}
    assert items["Zinc x"] == {"raw_name": "Zinc x", "count": 3, "latest_value": 7.5,
                               "latest_date": "2024-06-01", "unit": "mg"}
    assert items["Mucus"]["latest_value"] is None and items["Mucus"]["latest_date"] == "2024-03-01"


def test_map_to_catalog_marker_back_applies_and_shows_in_history(client, engine):
    _unmapped(engine, [(dt.date(2024, 1, 1), "Ферритин сыв", 50.0, None, "ng/mL")])
    r = client.post("/api/v1/review/alias", json={"raw_name": "Ферритин сыв", "marker_key": "ferritin",
                                                  "display_name": "Ferritin"})
    assert r.json() == {"updated": 1}
    assert client.get("/api/v1/review/unmapped").json() == []
    h = client.get("/api/v1/biomarkers/ferritin/history").json()
    assert [p["value"] for p in h["points"]] == [50.0] and h["system"] != "other"
    ru = {m["marker_key"]: m for m in client.get("/api/v1/biomarkers", headers=RU_H).json()}
    assert ru["ferritin"]["display_name"] != "Ferritin"  # Russian catalog name in the RU UI
    en = {m["marker_key"]: m for m in client.get("/api/v1/biomarkers").json()}
    assert en["ferritin"]["display_name"] == "Ferritin"


def test_ignore_hides_without_deleting(client, engine):
    _unmapped(engine, [(dt.date(2024, 1, 1), "Epithelium", None, "few", ""),
                       (dt.date(2024, 1, 1), "Mucus", None, "+", "")])
    assert client.post("/api/v1/review/ignore", json={"raw_name": "  epithelium "}).status_code == 204
    assert client.post("/api/v1/review/ignore", json={"raw_name": "EPITHELIUM"}).status_code == 204
    assert [i["raw_name"] for i in client.get("/api/v1/review/unmapped").json()] == ["Mucus"]
    from db.models import AppSetting
    with Session(engine) as s:
        assert s.get(AppSetting, "unmapped_ignored").value == ["epithelium"]
    assert "unmapped:epithelium" in {m["marker_key"] for m in client.get("/api/v1/biomarkers").json()}


def test_ignore_requires_a_name_localized(client):
    en = client.post("/api/v1/review/ignore", json={"raw_name": "  "})
    ru = client.post("/api/v1/review/ignore", json={"raw_name": ""}, headers=RU_H)
    assert en.status_code == ru.status_code == 422
    assert en.json()["detail"] == EN["http.review_name_required"]
    assert ru.json()["detail"] == RU["http.review_name_required"]


def test_catalog_marker_keeps_canonical_name_even_if_client_sends_russian(client, engine):
    _unmapped(engine, [(dt.date(2024, 1, 1), "Ферритин сыв", 50.0, None, "ng/mL")])
    client.post("/api/v1/review/alias", json={"raw_name": "Ферритин сыв", "marker_key": "ferritin",
                                              "display_name": "Ферритин"})
    en = {m["marker_key"]: m for m in client.get("/api/v1/biomarkers").json()}
    assert en["ferritin"]["display_name"] == "Ferritin"
