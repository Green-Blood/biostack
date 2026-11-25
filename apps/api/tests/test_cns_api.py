import datetime as dt


def _test(client, taps, days_ago=0):
    stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat()
    return client.post("/api/v1/cns/tests", json={"tap_count_10s": taps, "timestamp": stamp})


def test_first_tests_have_no_baseline(client):
    res = _test(client, 58, days_ago=3)
    assert res.status_code == 201
    assert res.json()["baseline_dev_pct"] is None and res.json()["baseline_samples"] == 0


def test_fourth_test_is_compared_with_the_previous_three(client):
    for days_ago in (3, 2, 1):
        _test(client, 50, days_ago)
    body = _test(client, 55).json()
    assert body["baseline_dev_pct"] == 10.0 and body["baseline_mean"] == 50.0 and body["baseline_samples"] == 3


def test_tap_count_must_be_sensible(client):
    assert client.post("/api/v1/cns/tests", json={"tap_count_10s": -1}).status_code == 422
    assert client.post("/api/v1/cns/tests", json={"tap_count_10s": 400}).status_code == 422


def test_timestamp_defaults_to_now(client):
    stamp = dt.datetime.fromisoformat(client.post("/api/v1/cns/tests", json={"tap_count_10s": 50}).json()["timestamp"])
    assert abs(dt.datetime.now(dt.timezone.utc) - stamp) < dt.timedelta(minutes=1)


def test_history_is_newest_first(client):
    _test(client, 40, days_ago=2)
    _test(client, 41, days_ago=1)
    assert [t["tap_count_10s"] for t in client.get("/api/v1/cns/tests").json()] == [41, 40]


def test_delete(client):
    test_id = _test(client, 50).json()["id"]
    assert client.delete(f"/api/v1/cns/tests/{test_id}").status_code == 204
    assert client.delete(f"/api/v1/cns/tests/{test_id}").status_code == 404


def test_demo_tests_never_feed_a_real_baseline(client, session):
    from db.models import CnsTest

    now = dt.datetime.now(dt.timezone.utc)
    session.add_all(CnsTest(timestamp=now - dt.timedelta(days=d), tap_count_10s=80, source="demo") for d in (1, 2, 3))
    session.commit()
    body = _test(client, 50).json()
    assert body["baseline_dev_pct"] is None and body["baseline_samples"] == 0
    for days_ago in (3, 2, 1):
        _test(client, 40, days_ago)
    body = _test(client, 44).json()
    assert (body["baseline_mean"], body["baseline_samples"]) == (42.5, 4)  # the three demo tests at 80 are ignored
