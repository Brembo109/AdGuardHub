from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Isolate the test run from any real deployment before app modules read settings.
os.environ["ADGUARDHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="adguardhub-tests-")
os.environ["ADGUARDHUB_SECRET_KEY"] = "test-secret-key"
os.environ.pop("ADGUARDHUB_ADMIN_USERNAME", None)
os.environ.pop("ADGUARDHUB_ADMIN_PASSWORD", None)

import httpx  # noqa: E402

from app import db  # noqa: E402
from app.adapters import ADAPTERS  # noqa: E402
from app.adapters import session as adapter_session  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.querylog import buffer  # noqa: E402
from app.services.sync import drain_background  # noqa: E402

from .fakes import FakeAdapter  # noqa: E402


@pytest_asyncio.fixture
async def fresh_db(tmp_path, monkeypatch) -> AsyncIterator[None]:
    """Point the engine at a per-test SQLite file and create the schema.

    The app's lifespan is deliberately not run: its background workers would poll
    real instances, and each test drives the pieces it cares about explicitly.
    """
    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ADGUARDHUB_SECRET_KEY", "test-secret-key")
    await db.dispose_db()
    await db.init_db()
    await buffer.clear()
    # Cached AdGuard sessions are process-wide; keep them from leaking between tests.
    adapter_session.store.reset()
    yield
    await drain_background()
    await db.dispose_db()
    get_settings.cache_clear()


@pytest.fixture
def fake_adapter(monkeypatch) -> type[FakeAdapter]:
    """Swap the AdGuard adapter for an in-memory double."""
    FakeAdapter.reset()
    monkeypatch.setitem(ADAPTERS, "adguard", FakeAdapter)
    return FakeAdapter


@pytest_asyncio.fixture
async def client(fresh_db, fake_adapter) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def auth_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """A client that has completed first-run setup and holds a session cookie."""
    response = await client.post(
        "/api/auth/setup", json={"username": "admin", "password": "supersecret"}
    )
    assert response.status_code == 200, response.text
    return client
