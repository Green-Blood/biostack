import datetime as dt
import json

import pytest
from sqlmodel import select

from db.models import BriefingCache, CorrelationCache, DailyMetric, EnvironmentalLog
from services.ai_provider import AiNotConfigured
from services.briefing import FALLBACK_LABEL, BriefingWriter, get_briefing
from services.clock import local_zone
from services.gemini_client import AiRequestError

ZONE = local_zone()
NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=ZONE).astimezone(dt.timezone.utc)
THREE = ["State of the day.", "Patterns found.", "Next steps."]


class FakeClient:
    def __init__(self, bullets=THREE, error: Exception | None = None):
        self.bullets, self.error, self.calls = bullets, error, []

    def generate_json(self, prompt, document, schema, mime_type="application/pdf"):
        self.calls.append((prompt, document, schema, mime_type))
        if self.error:
            raise self.error
        return {"bullets": self.bullets}


def _briefing(session, client: FakeClient, now=NOW, **options):
    return get_briefing(session, now, "23:00", ZONE, lambda: BriefingWriter(client), ai_enabled=True, **options)


def _unconfigured():
    raise AiNotConfigured("Add GEMINI_API_KEY to .env to enable this.")


def test_the_ai_writes_three_bullets_from_the_context_json(session):
    session.add(DailyMetric(metric_date=NOW.astimezone(ZONE).date(), hrv_sdnn=55.0))
    session.commit()
    client = FakeClient()
    briefing = _briefing(session, client)
    assert briefing.source == "ai" and briefing.bullets == THREE and briefing.label == "AI summary"
    prompt, document, schema, mime_type = client.calls[0]
    assert mime_type == "application/json" and json.loads(document)["daily_metrics"][0]["hrv_sdnn"] == 55.0
    assert schema["properties"]["bullets"]["minItems"] == 3 == schema["properties"]["bullets"]["maxItems"]
    assert "exactly 3" in prompt.lower()


def test_the_briefing_is_cached_for_the_day(session):
    client = FakeClient()
    _briefing(session, client)
    again = _briefing(session, client, now=NOW + dt.timedelta(hours=3))
    assert len(client.calls) == 1 and again.bullets == THREE and again.source == "ai"
    assert len(session.exec(select(BriefingCache)).all()) == 1


def test_a_new_day_asks_the_ai_again(session):
    client = FakeClient()
    _briefing(session, client)
    _briefing(session, client, now=NOW + dt.timedelta(days=1))
    assert len(client.calls) == 2


@pytest.mark.parametrize("client", [
    FakeClient(error=AiRequestError("down")),
    FakeClient(bullets=["only one"]),
    FakeClient(bullets=["a", "b", "c", "d"]),
    FakeClient(bullets=["a", "", "c"]),
])
def test_a_failed_or_malformed_ai_answer_falls_back_to_the_data_summary(session, client):
    briefing = _briefing(session, client)
    assert briefing.source == "fallback" and briefing.label == FALLBACK_LABEL == "Summary from your data"
    assert len(briefing.bullets) == 3 and briefing.can_retry is True
    (marker,) = session.exec(select(BriefingCache)).all()
    assert marker.failed is True and marker.bullets == []


def test_without_a_configured_ai_the_fallback_is_used_and_not_cached(session):
    briefing = get_briefing(session, NOW, "23:00", ZONE, _unconfigured, ai_enabled=True)
    assert briefing.source == "fallback" and len(briefing.bullets) == 3
    assert session.exec(select(BriefingCache)).all() == []


def test_the_fallback_on_an_empty_database_invents_no_numbers(session):
    bullets = get_briefing(session, NOW, "23:00", ZONE, _unconfigured, ai_enabled=True).bullets
    text = " ".join(bullets).replace("48 hours", "").replace("14 days", "")
    assert not any(char.isdigit() for char in text)
    assert "not enough" in bullets[0].lower() or "no risk score" in bullets[0].lower()


def test_the_fallback_reports_the_score_and_the_strongest_pattern(session):
    session.add_all([
        EnvironmentalLog(timestamp=NOW - dt.timedelta(hours=2), pm2_5=60.0, pressure_delta_24h=-9.0),
        CorrelationCache(target_metric="hrv_sdnn", trigger_key="caffeine_at_bedtime", correlation_score=-0.82,
                         lag_hours=24, confidence_pct=99.0, p_value=0.01, n_days=40),
    ])
    session.commit()
    first, second, third = get_briefing(session, NOW, "23:00", ZONE, _unconfigured, ai_enabled=True).bullets
    assert "100" in first and "high" in first
    assert "More caffeine late in the day goes with lower HRV the next day" in second and "40 days" in second
    assert "r =" not in second
    assert "pressure" in third.lower()


def test_with_the_setting_off_the_ai_is_never_called_and_the_summary_is_deterministic(session):
    client = FakeClient()
    calls = []
    briefing = get_briefing(session, NOW, "23:00", ZONE, lambda: calls.append("built") or BriefingWriter(client),
                            ai_enabled=False)
    assert briefing.source == "fallback" and briefing.label == FALLBACK_LABEL and briefing.can_retry is False
    assert calls == [] and client.calls == [] and session.exec(select(BriefingCache)).all() == []


def test_a_failure_is_the_days_only_attempt_until_the_owner_asks_again(session):
    client = FakeClient(error=AiRequestError("down"))
    for hours in (0, 2, 5):
        briefing = _briefing(session, client, now=NOW + dt.timedelta(hours=hours))
        assert briefing.source == "fallback" and briefing.can_retry is True
    assert len(client.calls) == 1
    client.error = None
    retried = _briefing(session, client, refresh=True)
    assert len(client.calls) == 2 and retried.source == "ai" and retried.can_retry is False
    assert _briefing(session, client).bullets == THREE and len(client.calls) == 2
    assert [b.failed for b in session.exec(select(BriefingCache))] == [False]


def test_an_unconfigured_ai_is_not_an_attempt(session):
    briefing = get_briefing(session, NOW, "23:00", ZONE, _unconfigured, ai_enabled=True)
    assert briefing.can_retry is False and session.exec(select(BriefingCache)).all() == []


def test_a_briefing_written_while_demo_rows_exist_is_tagged_demo(session):
    from db.models import SupplementLog

    session.add(SupplementLog(timestamp=NOW, item_name="Caffeine", source="demo"))
    session.commit()
    _briefing(session, FakeClient())
    assert [b.source for b in session.exec(select(BriefingCache))] == ["demo"]


def test_concurrent_first_loads_make_one_attempt_and_no_errors(tmp_path):
    import threading
    import time

    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'briefing.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    class SlowClient(FakeClient):
        def generate_json(self, *args, **kwargs):
            time.sleep(0.1)
            return super().generate_json(*args, **kwargs)

    client, results, errors = SlowClient(), [], []

    def load():
        try:
            with Session(engine) as own:
                results.append(_briefing(own, client).bullets)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure
            errors.append(exc)

    threads = [threading.Thread(target=load) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and len(client.calls) == 1 and results == [THREE] * 6


def test_correcting_sex_or_age_regenerates_the_days_briefing_once_but_weight_does_not(session):
    from db.models import BodyMeasurement, Profile

    session.add(Profile(id=1, sex="male", birth_date=dt.date(1990, 1, 1)))
    session.commit()
    client = FakeClient()
    _briefing(session, client)
    _briefing(session, client)
    assert len(client.calls) == 1
    session.add(BodyMeasurement(measured_on=NOW.date(), kind="weight", value=80))
    session.commit()
    _briefing(session, client)
    assert len(client.calls) == 1  # weight is not in the stamp
    session.get(Profile, 1).sex = "female"
    session.commit()
    _briefing(session, client)
    _briefing(session, client)
    assert len(client.calls) == 2
    session.get(Profile, 1).birth_date = dt.date(1960, 1, 1)
    session.commit()
    _briefing(session, client)
    _briefing(session, client)
    assert len(client.calls) == 3
