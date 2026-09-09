from datetime import datetime, timedelta, timezone

from app.domains.analytics.aggregation import (
    FIT_SCORE_BANDS,
    fit_score_bands,
    period_start,
    rate,
    weighted_average,
)

_NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)


class TestPeriodStart:
    def test_all_has_no_lower_bound(self):
        assert period_start("all", _NOW) is None

    def test_30d(self):
        assert period_start("30d", _NOW) == _NOW - timedelta(days=30)

    def test_90d(self):
        assert period_start("90d", _NOW) == _NOW - timedelta(days=90)

    def test_unknown_period_falls_through_to_no_bound(self):
        assert period_start("bogus", _NOW) is None


class TestRate:
    def test_zero_whole_is_zero_not_error(self):
        assert rate(5, 0) == 0.0

    def test_rounds_to_one_dp(self):
        assert rate(1, 3) == 33.3

    def test_full(self):
        assert rate(4, 4) == 100.0

    def test_can_exceed_100_is_not_clamped(self):
        # documents behaviour; callers must not pass part > whole for a "rate"
        assert rate(3, 2) == 150.0


class TestWeightedAverage:
    def test_none_when_no_weight(self):
        assert weighted_average([]) is None
        assert weighted_average([(12.0, 0)]) is None

    def test_weights_by_count(self):
        # (10 min avg over 1) + (20 min avg over 3) -> 17.5
        assert weighted_average([(10.0, 1), (20.0, 3)]) == 17.5

    def test_ignores_zero_weight_entries(self):
        assert weighted_average([(10.0, 2), (999.0, 0)]) == 10.0


class TestFitScoreBands:
    def test_empty(self):
        assert fit_score_bands([]) == dict.fromkeys(FIT_SCORE_BANDS, 0)

    def test_boundaries(self):
        counts = fit_score_bands([0, 49, 50, 69, 70, 84, 85, 100])
        assert counts == {"0-49": 2, "50-69": 2, "70-84": 2, "85-100": 2}

    def test_all_keys_always_present(self):
        counts = fit_score_bands([95, 96])
        assert set(counts) == set(FIT_SCORE_BANDS)
        assert counts["0-49"] == 0
