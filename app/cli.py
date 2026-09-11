"""CLI entry points for the periodic sweep scripts (review D06 / the
RabbitMQ+Airflow migration — see docs/plans/rabbitmq-airflow-migration.md).

Thin wrappers only: all business logic stays in `app/scripts/*.py`'s
`run()`/`main()` (including `sweep_advisory_lock`, untouched here). This
adds a proper subcommand shape, `--json` output, and predictable exit codes
for whatever invokes it — a human running `uv run ats-cli sweep ...`
directly, or Airflow's `SSHOperator` running
`docker compose run --rm app uv run ats-cli sweep ...` — in place of the
older `uv run python -m app.scripts.<name>` form (which still works
unchanged; this doesn't replace it, just adds a nicer front door).
"""

import asyncio
import json
import selectors

import typer

from app.scripts import (
    disqualify_overdue_applications,
    expire_overdue_assessment_attempts,
    purge_expired_revoked_tokens,
)

# pretty_exceptions_enable=False — this runs non-interactively under Airflow's
# SSHOperator; a plain traceback in a log stream beats Rich's box-drawing.
app = typer.Typer(help="ATS operational CLI.", pretty_exceptions_enable=False)
sweep_app = typer.Typer(
    help="Layer-1/layer-2 assessment sweep — see docs/decisions/D06"
)
app.add_typer(sweep_app, name="sweep")


def _run_sync(coro):
    """Same Windows event-loop fix every standalone script in this project
    uses (CLAUDE.md's "Async architecture" note) — psycopg's async driver
    can't run under asyncio.run()'s default ProactorEventLoop there."""
    return asyncio.run(
        coro,
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )


@sweep_app.command("expire-attempts")
def expire_attempts(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print {'expired': N} as JSON instead of the script's own log line.",
    ),
) -> None:
    """Expire overdue assessment attempts (layer 2 of the sweep). Must run
    *before* disqualify-applications in the same tick — a just-expired
    attempt needs to be visible to that check."""
    result = _run_sync(expire_overdue_assessment_attempts.main())
    if json_output:
        typer.echo(json.dumps({"expired": result}))
    if result is None:
        typer.echo(
            "skipped — another sweep run already held the advisory lock", err=True
        )


@sweep_app.command("disqualify-applications")
def disqualify_applications(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print {'checked': N, 'disqualified': N} as JSON, not a log line.",
    ),
) -> None:
    """Disqualify overdue applications that aren't fully assessed (layer 1
    of the sweep). Run *after* expire-attempts in the same tick — see
    app/scripts/disqualify_overdue_applications.py's module docstring."""
    result = _run_sync(disqualify_overdue_applications.main())
    if json_output:
        typer.echo(json.dumps(result if result is not None else {"skipped": True}))
    if result is None:
        typer.echo(
            "skipped — another sweep run already held the advisory lock", err=True
        )


@sweep_app.command("purge-expired-tokens")
def purge_expired_tokens(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print {'purged': N} as JSON instead of the script's own log line.",
    ),
) -> None:
    """Drop revoked-refresh-token denylist rows whose token has already
    expired — housekeeping unrelated to the assessment sweep above (it just
    rode the same timer under the old APScheduler setup); no shared
    advisory lock needed, see app/scripts/purge_expired_revoked_tokens.py's
    module docstring."""
    result = _run_sync(purge_expired_revoked_tokens.main())
    if json_output:
        typer.echo(json.dumps({"purged": result}))


if __name__ == "__main__":
    app()
