"""
Test bootstrap.

The environment is configured BEFORE any `app.*` module is imported so the
whole suite runs against a temporary SQLite database. This keeps tests
self-contained: no PostgreSQL or Redis instance is required and the local
development database is never touched.
"""
import atexit
import os
import shutil
import tempfile
import uuid

_TEST_DB_DIR = tempfile.mkdtemp(prefix="catalyst-tests-")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, f"catalyst_{uuid.uuid4().hex}.db")
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.db import Base, engine
from app.main import app


@pytest_asyncio.fixture
async def fresh_db():
    """Recreate the schema for every test and keep engine pools loop-local."""
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client(fresh_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
