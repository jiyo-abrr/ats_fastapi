"""F18 — migrations run cleanly against a real, disposable database, and the
ORM metadata matches the migrated schema."""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from alembic import command
from tests.integration.conftest import _TEST_URL


def _cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _TEST_URL)
    return cfg


def test_single_head():
    heads = ScriptDirectory.from_config(_cfg()).get_heads()
    assert len(heads) == 1, f"expected one migration head, got {heads}"


def test_autogenerate_detects_no_drift(_fresh_test_database):
    """`alembic check` — the migrated schema equals what the ORM models
    declare, so a future autogenerate wouldn't silently need a migration."""
    try:
        command.check(_cfg())
    except CommandError as exc:  # alembic raises this when a diff is found
        pytest.fail(f"schema drift between models and migrations:\n{exc}")


def test_full_downgrade_then_upgrade(_fresh_test_database):
    """A populated-deployment-style round trip: down to base, back to head."""
    cfg = _cfg()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
