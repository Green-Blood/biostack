"""Plain-language wording for a found link, and whether it helps or hurts.

The sign of r says whether the predictor and the target move together. What that means for the person depends on
two things the sign alone cannot know: what the predictor measures (a falling-pressure link is the same finding as
a rising-pressure link with the opposite sign) and whether a higher target value is good (HRV, deep sleep) or bad
(symptom severity). Each predictor is therefore described in one natural direction (`direction`), and the target
is stated as higher or lower in the person's own terms.
"""
from dataclasses import dataclass

from services.i18n import msg


@dataclass(frozen=True)
class PredictorWords:
    phrase: str
    direction: int  # +1: the phrase describes the predictor's value rising, -1: falling


@dataclass(frozen=True)
class TargetWords:
    higher: str
    lower: str
    higher_is_better: bool


PREDICTOR_DIRECTIONS = {"caffeine_at_bedtime": +1, "pm2_5": +1, "pressure_delta_24h": -1}
TARGET_HIGHER_IS_BETTER = {"hrv_sdnn": True, "sleep_deep_min": True, "symptom_severity": False}
FIXED_LAGS = (0, 24, 48)


def _when(lag_hours: int, lang: str) -> str:
    return msg(lang, f"when.{lag_hours}") if lag_hours in FIXED_LAGS else msg(lang, "when.other", hours=lag_hours)


def _predictor_words(key: str, lang: str) -> PredictorWords | None:
    if key in PREDICTOR_DIRECTIONS:
        return PredictorWords(msg(lang, f"pred.{key}"), PREDICTOR_DIRECTIONS[key])
    kind, _, name = key.partition(":")
    return PredictorWords(msg(lang, "pred.taking", name=name.lower()), +1) if kind in {"trigger", "protector"} and name else None


def _target_words(key: str, lang: str) -> TargetWords | None:
    if key not in TARGET_HIGHER_IS_BETTER:
        return None
    return TargetWords(msg(lang, f"target.{key}.higher"), msg(lang, f"target.{key}.lower"), TARGET_HIGHER_IS_BETTER[key])


def describe(predictor_key: str, target_key: str, r: float, lag_hours: int, lang: str = "en") -> tuple[str, str]:
    """The sentence for a link and its effect on the target: "worsens", "improves" or "unclear"."""
    predictor, target = _predictor_words(predictor_key, lang), _target_words(target_key, lang)
    when = _when(lag_hours, lang)
    if predictor is None or target is None or r == 0:
        subject = predictor.phrase if predictor else predictor_key.partition(":")[2].capitalize() or predictor_key.capitalize()
        outcome = (target.higher if r > 0 else target.lower) if target else target_key
        return msg(lang, "phrase.goes_with", subject=subject, outcome=outcome, when=when), "unclear"
    target_rises = (r > 0) == (predictor.direction > 0)
    good = target_rises == target.higher_is_better
    outcome = target.higher if target_rises else target.lower
    return msg(lang, "phrase.goes_with", subject=predictor.phrase, outcome=outcome, when=when), "improves" if good else "worsens"
