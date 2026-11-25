import datetime as dt


def _add(client, **fields):
    body = {"entry_date": "2026-11-10", "category": "symptom", "title": "Headache", "severity_1_10": 6, "body_location": "head", **fields}
    return client.post("/api/v1/journal", json=body)


def test_create_returns_the_entry(client):
    res = _add(client, description="After lunch")
    assert res.status_code == 201
    assert res.json() | {"id": 0} == {"id": 0, "entry_date": "2026-11-10", "category": "symptom", "title": "Headache",
                                      "description": "After lunch", "severity_1_10": 6, "body_location": "head"}


def test_entry_date_defaults_to_today(client):
    body = {"category": "note", "title": "Slept well"}
    assert client.post("/api/v1/journal", json=body).json()["entry_date"] == dt.date.today().isoformat()


def test_severity_must_be_one_to_ten(client):
    assert _add(client, severity_1_10=0).status_code == 422
    assert _add(client, severity_1_10=11).status_code == 422
    assert _add(client, severity_1_10=None).status_code == 201


def test_title_and_category_are_validated(client):
    assert _add(client, title=" ").status_code == 422
    assert _add(client, category="rant").status_code == 422


def test_list_is_newest_first_and_filters(client):
    _add(client, entry_date="2026-11-01", title="Old")
    _add(client, entry_date="2026-11-09", category="doctor_visit", title="Visit", severity_1_10=None)
    _add(client, entry_date="2026-11-10", title="New")
    assert [e["title"] for e in client.get("/api/v1/journal").json()] == ["New", "Visit", "Old"]
    assert [e["title"] for e in client.get("/api/v1/journal", params={"category": "symptom"}).json()] == ["New", "Old"]
    assert [e["title"] for e in client.get("/api/v1/journal", params={"from": "2026-11-05"}).json()] == ["New", "Visit"]
    assert [e["title"] for e in client.get("/api/v1/journal", params={"to": "2026-11-05"}).json()] == ["Old"]


def test_patch_changes_only_the_sent_fields(client):
    entry_id = _add(client).json()["id"]
    res = client.patch(f"/api/v1/journal/{entry_id}", json={"severity_1_10": 3})
    assert res.json()["severity_1_10"] == 3 and res.json()["title"] == "Headache"
    assert client.patch(f"/api/v1/journal/{entry_id}", json={"severity_1_10": 12}).status_code == 422
    assert client.patch("/api/v1/journal/999", json={"title": "x"}).status_code == 404


def test_delete(client):
    entry_id = _add(client).json()["id"]
    assert client.delete(f"/api/v1/journal/{entry_id}").status_code == 204
    assert client.delete(f"/api/v1/journal/{entry_id}").status_code == 404
