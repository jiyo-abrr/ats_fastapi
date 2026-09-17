from app.domains.applications.enums import (
    EVALUATION_ELIGIBLE_STATUSES,
    allowed_transitions_for,
    can_withdraw,
)


class TestAllowedTransitionsFor:
    def test_applied_can_advance_or_be_denied(self):
        assert allowed_transitions_for("applied") == ["denied", "prescreening"]

    def test_prescreening(self):
        assert allowed_transitions_for("prescreening") == ["denied", "interview"]

    def test_interview_decides(self):
        assert allowed_transitions_for("interview") == ["failed", "success"]

    def test_terminal_statuses_have_none(self):
        for terminal in ("denied", "success", "failed", "withdrawn", "disqualified"):
            assert allowed_transitions_for(terminal) == []

    def test_unknown_status_is_empty_not_error(self):
        assert allowed_transitions_for("bogus") == []


class TestCanWithdraw:
    def test_true_for_active_stages(self):
        assert all(can_withdraw(s) for s in ("applied", "prescreening", "interview"))

    def test_false_for_terminal_and_unknown(self):
        assert not any(
            can_withdraw(s)
            for s in ("denied", "success", "failed", "withdrawn", "disqualified", "x")
        )


class TestEvaluationEligibleStatuses:
    def test_excludes_withdrawn_and_disqualified(self):
        assert "withdrawn" not in EVALUATION_ELIGIBLE_STATUSES
        assert "disqualified" not in EVALUATION_ELIGIBLE_STATUSES

    def test_includes_every_other_status(self):
        assert EVALUATION_ELIGIBLE_STATUSES == sorted(
            ["applied", "prescreening", "interview", "denied", "success", "failed"]
        )
