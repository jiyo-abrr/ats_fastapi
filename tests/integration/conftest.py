"""Integration test harness — a real, throwaway PostgreSQL database.

Addresses maintainability review F06. The harness-gated findings (F02 races,
F03 booking integrity, F04 template lifecycle, F08 query counts, F18
migrations) build on the fixtures here.

The suite is **skipped automatically** when no Postgres is reachable, so
`uv run pytest` on a laptop with nothing running still runs the unit tests.
CI runs it with a `postgres` service.
"""

from collections.abc import AsyncIterator, Callable

import psycopg
import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command
from app.core.config import settings

_BASE_URL = settings.database_url  # postgresql+psycopg://user:pass@host:port/db
_TEST_DB = _BASE_URL.rsplit("/", 1)[-1] + "_test"
_TEST_URL = _BASE_URL.rsplit("/", 1)[0] + "/" + _TEST_DB
_ADMIN_DSN = _BASE_URL.replace("+psycopg", "").rsplit("/", 1)[0] + "/postgres"


def _postgres_reachable() -> bool:
    try:
        with psycopg.connect(_ADMIN_DSN, connect_timeout=2):
            return True
    except Exception:
        return False


_SKIP = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="no PostgreSQL reachable — integration tests skipped",
)


def pytest_collection_modifyitems(items):
    for item in items:
        if "/tests/integration/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(_SKIP)


@pytest.fixture(scope="session")
def _fresh_test_database() -> None:
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{_TEST_DB}"')

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _TEST_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def test_engine(_fresh_test_database) -> AsyncIterator:
    engine = create_async_engine(_TEST_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    """A session inside a rolled-back outer transaction — `commit()` in the
    test becomes a savepoint release, so nothing persists across tests."""
    async with test_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
async def client(db_session) -> AsyncIterator[AsyncClient]:
    from app.core.database import get_db
    from app.main import app

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


_ALL_TABLES: list[str] | None = None


# Seeded by migrations and relied on by every test — never truncate these.
_KEEP_TABLES = frozenset(
    {"alembic_version", "roles", "permissions", "role_permissions"}
)


async def _truncate_all(engine) -> None:
    global _ALL_TABLES
    async with engine.begin() as conn:
        if _ALL_TABLES is None:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            _ALL_TABLES = [r[0] for r in rows if r[0] not in _KEEP_TABLES]
        if _ALL_TABLES:
            await conn.execute(
                text(
                    "TRUNCATE "
                    + ", ".join(f'"{t}"' for t in _ALL_TABLES)
                    + " RESTART IDENTITY CASCADE"
                )
            )


@pytest.fixture
async def committing_session(
    test_engine,
) -> AsyncIterator[Callable[[], AsyncSession]]:
    """Independently-committing sessions for two-connection race tests. Every
    table is truncated afterwards."""
    maker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    opened: list[AsyncSession] = []

    def _factory() -> AsyncSession:
        s = maker()
        opened.append(s)
        return s

    try:
        yield _factory
    finally:
        for s in opened:
            await s.close()
        await _truncate_all(test_engine)
