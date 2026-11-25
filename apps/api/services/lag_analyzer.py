"""Finds lagged relationships between daily predictors (caffeine at bedtime, air quality, ...) and daily targets.

Every series maps a calendar date to one number. A lag of L hours pairs the target of day D with the predictor
as it was L hours earlier. Whole-day lags (0, 24, 48 h) read the predictor of day D - L/24 directly; half-day
lags (12, 36 h) linearly interpolate between the two neighbouring days, and are skipped for a day when either
neighbour is missing. So "+24h" means "the day before".

For each (target, predictor, lag) with at least MIN_OVERLAP_DAYS paired days the Pearson and Spearman
coefficients are computed with SciPy, with their p-values. A pair is reported when its best lag (largest |r|)
has Pearson p < MAX_P_VALUE and |r| > MIN_ABS_R. Five lags are tried per pair, so a hit is a lead to check,
not proof; the confidence shown is (1 - p), not a guarantee.
"""
import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
from scipy import stats

LAGS_HOURS = (0, 12, 24, 36, 48)
MIN_OVERLAP_DAYS = 14
MIN_ABS_R = 0.5
MAX_P_VALUE = 0.05

DailySeries = dict[dt.date, float]


@dataclass(frozen=True)
class Correlation:
    target: str
    predictor: str
    lag_hours: int
    pearson_r: float
    pearson_p: float
    spearman_r: float
    spearman_p: float
    n_days: int


@dataclass(frozen=True)
class TargetReport:
    target: str
    status: str  # "ok" | "insufficient_data"
    days: int
    pairs_tested: int
    reason: str = ""


@dataclass
class AnalysisResult:
    correlations: list[Correlation] = field(default_factory=list)
    targets: list[TargetReport] = field(default_factory=list)


def _predictor_at(predictor: DailySeries, day: dt.date, lag_hours: int) -> float | None:
    whole_days, fraction = divmod(lag_hours / 24, 1)
    newer = predictor.get(day - dt.timedelta(days=int(whole_days)))
    if fraction == 0:
        return newer
    older = predictor.get(day - dt.timedelta(days=int(whole_days) + 1))
    if newer is None or older is None:
        return None
    return (1 - fraction) * newer + fraction * older


def shifted_pairs(predictor: DailySeries, target: DailySeries, lag_hours: int) -> tuple[list[float], list[float]]:
    """Predictor values (as they were lag_hours earlier) next to the target of each day, in date order."""
    xs: list[float] = []
    ys: list[float] = []
    for day in sorted(target):
        value = _predictor_at(predictor, day, lag_hours)
        if value is not None:
            xs.append(value)
            ys.append(target[day])
    return xs, ys


def correlate(
    predictor: DailySeries, target: DailySeries, lag_hours: int, predictor_key: str = "", target_key: str = "",
) -> Correlation | None:
    """None when fewer than MIN_OVERLAP_DAYS days pair up or either side never varies."""
    xs, ys = shifted_pairs(predictor, target, lag_hours)
    if len(xs) < MIN_OVERLAP_DAYS or np.ptp(xs) == 0 or np.ptp(ys) == 0:
        return None
    pearson = stats.pearsonr(xs, ys)
    spearman = stats.spearmanr(xs, ys)
    return Correlation(
        target=target_key, predictor=predictor_key, lag_hours=lag_hours,
        pearson_r=float(pearson.statistic), pearson_p=float(pearson.pvalue),
        spearman_r=float(spearman.statistic), spearman_p=float(spearman.pvalue), n_days=len(xs),
    )


def _is_notable(found: Correlation) -> bool:
    return found.pearson_p < MAX_P_VALUE and abs(found.pearson_r) > MIN_ABS_R and not math.isnan(found.spearman_r)


def _lag_scan(predictor_key: str, predictor: DailySeries, target_key: str, target: DailySeries) -> list[Correlation]:
    scan = (correlate(predictor, target, lag, predictor_key, target_key) for lag in LAGS_HOURS)
    return [found for found in scan if found is not None]


def _report(target_key: str, target: DailySeries, scans: list[list[Correlation]]) -> TargetReport:
    pairs_tested = sum(len(scan) for scan in scans)
    if len(target) < MIN_OVERLAP_DAYS:
        reason = f"Only {len(target)} days of data so far; at least {MIN_OVERLAP_DAYS} are needed."
        return TargetReport(target_key, "insufficient_data", len(target), pairs_tested, reason)
    if pairs_tested == 0:
        reason = f"No logged predictor overlaps this on {MIN_OVERLAP_DAYS} days yet; keep logging both."
        return TargetReport(target_key, "insufficient_data", len(target), pairs_tested, reason)
    return TargetReport(target_key, "ok", len(target), pairs_tested)


def analyze(targets: dict[str, DailySeries], predictors: dict[str, DailySeries]) -> AnalysisResult:
    result = AnalysisResult()
    for target_key, target in targets.items():
        scans = [_lag_scan(key, series, target_key, target) for key, series in predictors.items()]
        result.targets.append(_report(target_key, target, scans))
        for scan in scans:
            notable = [found for found in scan if _is_notable(found)]
            if notable:
                result.correlations.append(max(notable, key=lambda found: abs(found.pearson_r)))
    return result
