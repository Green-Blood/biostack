from config import settings
from main import app
from routers.insights import get_insight_client_factory
from services.fake_ai import FakeGeminiClient
from tests.test_api_labs import seed


class Counting(FakeGeminiClient):
    calls = 0

    def generate_grounded(self, prompt, document, mime_type="application/json"):
        Counting.calls += 1
        return super().generate_grounded(prompt, document, mime_type)


def _use_ai(client, engine):
    seed(engine)
    Counting.calls = 0
    app.dependency_overrides[get_insight_client_factory] = lambda: Counting
    client.patch("/api/v1/settings", json={"ai_briefing": True})


def test_overview_reports_the_share_in_range_without_ai(client, engine):
    seed(engine)  # vitamin D 31 and ferritin 50 are both in range
    body = client.get("/api/v1/insights/overview").json()
    assert (body["ai_enabled"], body["health_pct"], body["ok"], body["total"]) == (False, 100, 2, 2)
    assert "summary" not in body


def test_system_guide_needs_the_ai_setting(client, engine):
    seed(engine)
    assert client.get("/api/v1/insights/system/vitamins").json() == {"ai_enabled": False}


def test_overview_and_panel_are_cached_until_refresh(client, engine):
    _use_ai(client, engine)
    first = client.get("/api/v1/insights/overview").json()
    assert first["summary"] == "Test summary." and first["actions"][0]["title"] == "Sleep"
    client.get("/api/v1/insights/overview")
    assert Counting.calls == 1
    client.get("/api/v1/insights/overview?refresh=true")
    assert Counting.calls == 2
    panel = client.get("/api/v1/insights/system/vitamins").json()
    assert panel["markers"][0]["key"] == "ferritin" and panel["tests_skip"]
    client.get("/api/v1/insights/system/vitamins")
    assert Counting.calls == 3


def test_marker_guide_is_cached_and_unknown_marker_is_404(client, engine):
    _use_ai(client, engine)
    body = client.get("/api/v1/insights/marker/ferritin").json()
    assert body["meaning"] == "Iron stores." and body["tests_worth_it"]
    client.get("/api/v1/insights/marker/ferritin")
    assert Counting.calls == 1
    assert client.get("/api/v1/insights/marker/nope").status_code == 404
    assert client.get("/api/v1/insights/marker/unmapped:mucus").json()["meaning"]  # text-only and unmapped markers are explained too


def test_parse_finds_the_json_inside_prose_and_fences():
    from services.insights import _parse
    assert _parse('Sure {not json} here:\n```json\n{"a": {"b": 1}}\n```\nDone.') == {"a": {"b": 1}}


def test_empty_panel_is_404(client, engine):
    _use_ai(client, engine)
    assert client.get("/api/v1/insights/system/kidney").status_code == 404
