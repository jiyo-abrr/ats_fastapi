from app.domains.analytics.repository import _recommend
from app.domains.job_posts.enums import JobPostStatus

_PUBLISHED = JobPostStatus.PUBLISHED.value
_BASE = {
    "status": _PUBLISHED,
    "applied": 10,
    "screened": 5,
    "passed": 0,
    "accepted": 0,
    "avg_score": None,
    "posting_duration_days": 10,
}


def _rec(**overrides) -> str | None:
    return _recommend(**{**_BASE, **overrides})


class TestRecommend:
    def test_non_published_status_has_no_recommendation(self):
        assert _rec(status=JobPostStatus.DRAFT.value) is None
        assert _rec(status=JobPostStatus.CLOSED.value) is None

    def test_enough_passed_recommends_closing(self):
        assert (
            _rec(passed=3)
            == "Close the posting after sufficient qualified applicants are identified"
        )

    def test_any_accepted_recommends_closing_even_with_few_passed(self):
        assert (
            _rec(passed=0, accepted=1)
            == "Close the posting after sufficient qualified applicants are identified"
        )

    def test_high_avg_score_with_passed_prioritizes_high_scorers(self):
        assert _rec(passed=1, avg_score=85.0) == "Prioritize high-scoring candidates"

    def test_passed_without_high_score_schedules_interviews(self):
        assert _rec(passed=1, avg_score=50.0) == "Schedule interviews"
        assert _rec(passed=1, avg_score=None) == "Schedule interviews"

    def test_low_turnout_and_fresh_posting_keeps_promoting(self):
        assert (
            _rec(applied=2, posting_duration_days=5) == "Continue promoting the posting"
        )

    def test_low_turnout_and_stale_posting_extends(self):
        assert _rec(applied=2, posting_duration_days=30) == "Extend the posting period"

    def test_low_turnout_with_unknown_duration_keeps_promoting(self):
        assert (
            _rec(applied=2, posting_duration_days=None)
            == "Continue promoting the posting"
        )

    def test_low_screen_rate_flags_requirements_review(self):
        assert _rec(applied=10, screened=2) == "Review job requirements"

    def test_healthy_turnout_and_screen_rate_keeps_promoting(self):
        assert _rec(applied=10, screened=8) == "Continue promoting the posting"
