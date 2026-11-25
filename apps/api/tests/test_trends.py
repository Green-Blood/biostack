from services.trends import Point, compute_deltas


def P(d, v, lo=30.0, hi=100.0):
    return Point(date=d, value=v, ref_min=lo, ref_max=hi)


def test_deltas_toward_range():
    ds = compute_deltas([P("2022-01-01", 18), P("2023-01-01", 24), P("2024-01-01", 31)])
    assert [(d.abs, round(d.pct, 1), d.toward_range) for d in ds] == [(6, 33.3, True), (7, 29.2, True)]
    assert (ds[0].from_date, ds[0].to_date) == ("2022-01-01", "2023-01-01")


def test_deltas_away_from_range_and_none_when_both_inside():
    assert compute_deltas([P("a", 40), P("b", 20)])[0].toward_range is False
    assert compute_deltas([P("a", 40), P("b", 50)])[0].toward_range is None


def test_single_point_has_no_deltas():
    assert compute_deltas([P("a", 10)]) == []


def test_zero_previous_value_has_no_pct():
    d = compute_deltas([P("a", 0), P("b", 5)])[0]
    assert d.abs == 5 and d.pct is None


def test_no_reference_range_gives_none():
    d = compute_deltas([P("a", 1, None, None), P("b", 2, None, None)])[0]
    assert d.toward_range is None


def test_both_inside_range_is_reported_as_stayed_in_range():
    d = compute_deltas([P("a", 40), P("b", 50)])[0]
    assert d.toward_range is None and d.stayed_in_range is True


def test_no_range_is_not_stayed_in_range():
    d = compute_deltas([P("a", 1, None, None), P("b", 2, None, None)])[0]
    assert d.stayed_in_range is False
