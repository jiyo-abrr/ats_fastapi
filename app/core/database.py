from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# Sync engine/session: used only by Alembic (alembic/env.py) and one-off
# scripts (app/scripts/create_admin.py) that don't need to share the app's
# async session. The running FastAPI app never uses these.
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Async engine/session: what the app actually uses via get_db(). Same driver
# (psycopg) and URL as the sync engine above — SQLAlchemy's psycopg dialect
# dispatches sync vs async purely based on create_engine vs create_async_engine.
async_engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, autoflush=False, autocommit=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as db:
        yield db
