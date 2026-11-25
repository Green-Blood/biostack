import pytest

from services.correlation_phrases import describe


@pytest.mark.parametrize("predictor, target, r, lag, phrase, effect", [
    ("caffeine_at_bedtime", "hrv_sdnn", -0.7, 24, "More caffeine late in the day goes with lower HRV the next day", "worsens"),
    ("caffeine_at_bedtime", "sleep_deep_min", 0.6, 0, "More caffeine late in the day goes with more deep sleep the same day", "improves"),
    ("pm2_5", "symptom_severity", 0.6, 12, "Higher PM2.5 air pollution goes with worse symptoms about 12 hours later", "worsens"),
    ("pressure_delta_24h", "symptom_severity", -0.6, 0, "Falling air pressure goes with worse symptoms the same day", "worsens"),
    ("pressure_delta_24h", "symptom_severity", 0.6, 0, "Falling air pressure goes with milder symptoms the same day", "improves"),
    ("pressure_delta_24h", "hrv_sdnn", -0.55, 48, "Falling air pressure goes with higher HRV two days later", "improves"),
    ("protector:magnesium", "sleep_deep_min", 0.6, 24, "Taking magnesium goes with more deep sleep the next day", "improves"),
    ("trigger:alcohol", "hrv_sdnn", -0.6, 36, "Taking alcohol goes with lower HRV about 36 hours later", "worsens"),
])
def test_phrase_and_effect_follow_the_sign_and_what_each_side_measures(predictor, target, r, lag, phrase, effect):
    assert describe(predictor, target, r, lag) == (phrase, effect)


def test_unknown_variables_are_reported_as_unclear_without_a_made_up_direction():
    phrase, effect = describe("mystery", "hrv_sdnn", 0.6, 0)
    assert effect == "unclear" and "Mystery" in phrase and "HRV" in phrase
    assert describe("pm2_5", "mystery", 0.6, 0)[1] == "unclear"


def test_a_zero_correlation_is_unclear():
    assert describe("pm2_5", "hrv_sdnn", 0.0, 0)[1] == "unclear"
