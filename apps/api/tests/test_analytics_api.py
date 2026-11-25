import datetime as dt

import pytest
from sqlmodel import Session

from main import app
from routers.analytics import get_briefing_writer_factory
from services.briefing_writer import BriefingWriter
from services.demo_data import PLANTED_LAGS, seed_demo

BULLETS = ["State.", "Patterns.", "Steps."]


class FakeClient:
    def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
        return {"bullets": BULLETS}


def _unconfigured():
    from services.ai_provider import AiNotConfigured
    raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this.")


@pytest.fixture
def demo(engine):
    with Session(engine) as session:
        seed_demo(session, dt.datetime.now(dt.timezone.utc).astimezone().date())


def _ai_setting(client, on: bool) -> None:
    current = client.get("/api/v1/settings").json()
    body = {k: current[k] for k in ("latitude", "longitude", "bedtime", "timezone")}
    assert client.put("/api/v1/settings", json={**body, "ai_briefing": on}).status_code == 200


@pytest.fixture
def ai(client):
    _ai_setting(client, True)
    app.dependency_overrides[get_briefing_writer_factory] = lambda: (lambda: BriefingWriter(FakeClient()))
    yield
    app.dependency_overrides.pop(get_briefing_writer_factory, None)


@pytest.fixture
def no_ai(client):
    _ai_setting(client, True)
    app.dependency_overrides[get_briefing_writer_factory] = lambda: _unconfigured
    yield
    app.dependency_overrides.pop(get_briefing_writer_factory, None)


@pytest.mark.parametrize("method, path", [
    ("post", "/api/v1/analytics/recompute"), ("get", "/api/v1/analytics/correlations"),
    ("get", "/api/v1/analytics/risk"), ("get", "/api/v1/analytics/briefing"), ("get", "/api/v1/analytics/graph"),
    ("get", "/api/v1/meta/demo"),
])
def test_every_endpoint_needs_the_token(client, method, path):
    assert getattr(client, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_correlations_before_any_recompute_say_so(client):
    body = client.get("/api/v1/analytics/correlations").json()
    assert body["computed"] is False and body["correlations"] == [] and body["targets"] == []


def test_recompute_then_read_the_planted_correlations(client, demo):
    recomputed = client.post("/api/v1/analytics/recompute").json()
    assert {t["target"] for t in recomputed["targets"]} == {"hrv_sdnn", "sleep_deep_min", "symptom_severity"}
    body = client.get("/api/v1/analytics/correlations").json()
    assert body["computed"] is True
    found = {(c["trigger"], c["target"]): c for c in body["correlations"]}
    assert set(found) == set(PLANTED_LAGS)
    caffeine = found[("caffeine_at_bedtime", "hrv_sdnn")]
    assert caffeine["lag_hours"] == 24 and caffeine["lag_label"] == "+24h" and caffeine["r"] < -0.5
    assert caffeine["p_value"] < 0.05 and caffeine["n_days"] >= 14 and caffeine["trigger_label"] == "Caffeine left at bedtime"
    assert found[("pressure_delta_24h", "symptom_severity")]["lag_label"] == "same day"
    assert caffeine["effect"] == "worsens" and caffeine["phrase"].startswith("More caffeine")
    assert "confidence_pct" not in caffeine


def test_recompute_on_little_data_reports_why(client):
    body = client.post("/api/v1/analytics/recompute").json()
    assert body["targets"] == [] and body["correlations"] == []


def test_risk_without_data_has_no_score(client):
    body = client.get("/api/v1/analytics/risk").json()
    assert body["score"] is None and body["alert"] is False and body["reason"]
    assert len(body["factors"]) == 6


def test_risk_with_data_lists_a_breakdown(client, demo):
    body = client.get("/api/v1/analytics/risk").json()
    assert 0 <= body["score"] <= 100
    assert all({"key", "label", "weight", "points", "detail", "has_data"} <= set(f) for f in body["factors"])


def test_briefing_from_the_ai_is_labelled(client, ai):
    first = client.get("/api/v1/analytics/briefing").json()
    assert first["source"] == "ai" and first["bullets"] == BULLETS


def test_briefing_with_the_setting_off_makes_no_ai_call(client, demo):
    built = []
    app.dependency_overrides[get_briefing_writer_factory] = lambda: (lambda: built.append(1) or BriefingWriter(FakeClient()))
    try:
        body = client.get("/api/v1/analytics/briefing").json()
    finally:
        app.dependency_overrides.pop(get_briefing_writer_factory, None)
    assert built == [] and body["source"] == "fallback" and body["ai_enabled"] is False and body["can_retry"] is False
    assert body["label"] == "Summary from your data"


def test_refresh_makes_a_new_attempt_only_when_the_setting_is_on(client, ai):
    assert client.get("/api/v1/analytics/briefing").json()["source"] == "ai"
    assert client.post("/api/v1/analytics/briefing/refresh").json()["source"] == "ai"
    _ai_setting(client, False)
    res = client.post("/api/v1/analytics/briefing/refresh")
    assert res.status_code == 409 and "Settings" in res.json()["detail"]


def test_briefing_falls_back_with_its_label(client, demo, no_ai):
    body = client.get("/api/v1/analytics/briefing").json()
    assert body["source"] == "fallback" and body["label"] == "Summary from your data" and len(body["bullets"]) == 3


def test_graph_has_four_node_kinds_and_weighted_lagged_edges(client, demo):
    client.post("/api/v1/analytics/recompute")
    graph = client.get("/api/v1/analytics/graph").json()
    kinds = {n["kind"] for n in graph["nodes"]}
    assert kinds == {"symptom", "trigger", "protector", "biomarker"}
    nodes = {n["id"] for n in graph["nodes"]}
    assert len(graph["edges"]) == 3
    edge = next(e for e in graph["edges"] if e["source"] == "caffeine_at_bedtime")
    assert edge["target"] == "hrv_sdnn" and edge["lag_hours"] == 24 and edge["lagged"] is True
    assert edge["lag_label"] == "+24h" and edge["strength"] == abs(edge["r"]) > 0.5
    assert all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])
    assert graph["notes"] == []
    assert edge["phrase"] == "More caffeine late in the day goes with lower HRV the next day" and edge["effect"] == "worsens"
    assert edge["n_days"] >= 14 and 0 < edge["p_value"] < 0.05
    pressure = next(e for e in graph["edges"] if e["source"] == "pressure_delta_24h")
    assert pressure["phrase"] == "Falling air pressure goes with worse symptoms the same day" and pressure["effect"] == "worsens"
    magnesium = next(e for e in graph["edges"] if e["source"] == "protector:magnesium")
    assert magnesium["effect"] == "improves"


def test_graph_without_findings_explains_what_is_missing(client):
    graph = client.get("/api/v1/analytics/graph").json()
    assert graph["edges"] == [] and graph["notes"]


def test_demo_status_follows_the_rows(client, engine):
    assert client.get("/api/v1/meta/demo").json() == {"demo": False, "counts": {}}
    with Session(engine) as session:
        seed_demo(session, dt.date(2026, 3, 10))
    body = client.get("/api/v1/meta/demo").json()
    assert body["demo"] is True and body["counts"]["DailyMetric"] == 60
