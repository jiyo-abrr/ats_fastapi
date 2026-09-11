"""app/cli.py — thin Typer wrappers around app/scripts/*.py's main(). These
tests only prove the CLI wiring (exit codes, --json output, the "skipped"
message when the advisory lock is already held); the actual sweep logic is
covered by app/scripts/*.py's own tests and tests/integration/."""

import json

from typer.testing import CliRunner

from app.cli import app
from app.scripts import (
    disqualify_overdue_applications,
    expire_overdue_assessment_attempts,
)

runner = CliRunner()


class TestExpireAttempts:
    def test_reports_the_count_as_json(self, monkeypatch):
        async def fake_main():
            return 3

        monkeypatch.setattr(expire_overdue_assessment_attempts, "main", fake_main)

        result = runner.invoke(app, ["sweep", "expire-attempts", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"expired": 3}

    def test_plain_invocation_exits_zero_without_json(self, monkeypatch):
        async def fake_main():
            return 0

        monkeypatch.setattr(expire_overdue_assessment_attempts, "main", fake_main)

        result = runner.invoke(app, ["sweep", "expire-attempts"])

        assert result.exit_code == 0

    def test_reports_skip_when_the_advisory_lock_is_held(self, monkeypatch):
        async def fake_main():
            return None

        monkeypatch.setattr(expire_overdue_assessment_attempts, "main", fake_main)

        result = runner.invoke(app, ["sweep", "expire-attempts"])

        assert result.exit_code == 0
        assert "skipped" in result.output

    def test_a_raised_exception_exits_nonzero(self, monkeypatch):
        async def fake_main():
            raise RuntimeError("db unreachable")

        monkeypatch.setattr(expire_overdue_assessment_attempts, "main", fake_main)

        result = runner.invoke(app, ["sweep", "expire-attempts"])

        assert result.exit_code != 0


class TestDisqualifyApplications:
    def test_reports_checked_and_disqualified_as_json(self, monkeypatch):
        async def fake_main():
            return {"checked": 12, "disqualified": 4}

        monkeypatch.setattr(disqualify_overdue_applications, "main", fake_main)

        result = runner.invoke(app, ["sweep", "disqualify-applications", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"checked": 12, "disqualified": 4}

    def test_reports_skip_when_the_advisory_lock_is_held(self, monkeypatch):
        async def fake_main():
            return None

        monkeypatch.setattr(disqualify_overdue_applications, "main", fake_main)

        result = runner.invoke(app, ["sweep", "disqualify-applications", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"skipped": True}
