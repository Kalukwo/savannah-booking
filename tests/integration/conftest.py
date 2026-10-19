"""Integration fixtures: real PostgreSQL via TEST_DATABASE_URL.

The app's session dependency is overridden with sessions bound to the test
database, so no test can reach real data.
"""
import asyncio
import os
from datetime import datetime

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.timezone import EAT
from app.db.session import get_session
from app.main import create_app


def _test_url() -> str:
    """Resolve the test database through the same Settings object the app uses.

    Reading Settings rather than os.getenv keeps one code path for all three
    environments: a local .env file, GitHub Secrets injected as env vars in CI,
    and dashboard env vars on the deployed host. pydantic-settings already
    normalises postgres:// and sslmode=, so no duplication here.
    """
    url = get_settings().async_test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set (env var or .env file)")
    return url


async def _reset_schema(url: str) -> None:
    # Drop the schema wholesale, including alembic_version. Dropping only the
    # tables would leave the version row behind, and Alembic would then skip
    # the migration while the tables were missing.
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    os.environ["DATABASE_URL"] = url
    # Alembic's env.py calls asyncio.run(); pytest already owns a loop, so the
    # migration runs in a worker thread where a fresh loop is allowed.
    await asyncio.to_thread(command.upgrade, cfg, "head")


@pytest.fixture
async def client():
    url = _test_url()
    await _reset_schema(url)

    # poolclass=NullPool: each request opens its own connection, which makes
    # the concurrency test exercise real database contention.
    engine = create_async_engine(url, poolclass=NullPool)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await engine.dispose()


@pytest.fixture
def future_day():
    # A Monday well ahead of any real "now".
    return datetime(2027, 3, 1, tzinfo=EAT)
