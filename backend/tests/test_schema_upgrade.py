"""Adding a column to an existing database.

``create_all`` creates missing tables but never alters an existing one, so a new
model column would leave every running installation querying a column its
database does not have. These tests hold that door shut.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from app import db


async def _columns(conn) -> set[str]:
    rows = await conn.execute(text("PRAGMA table_info(instances)"))
    return {row[1] for row in rows}


async def test_a_new_column_is_added_to_an_existing_table(fresh_db) -> None:
    engine = db.get_engine()

    # Stand in for a database created before the column existed.
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE instances DROP COLUMN version"))
        assert "version" not in await _columns(conn)

    await db.init_db()

    async with engine.begin() as conn:
        assert "version" in await _columns(conn)


async def test_the_upgrade_keeps_existing_rows(fresh_db) -> None:
    """An operator's instances must survive the column being added."""
    engine = db.get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO instances (name, base_url, adapter, username,"
                " password_encrypted, verify_tls, enabled, status, version,"
                " last_error, created_at)"
                " VALUES ('kept', 'http://a', 'adguard', 'admin', '', 1, 1,"
                " 'online', 'v0.107.64', '', '2026-01-01')"
            )
        )
        await conn.execute(text("ALTER TABLE instances DROP COLUMN version"))

    await db.init_db()

    async with engine.begin() as conn:
        row = (await conn.execute(text("SELECT name, version FROM instances"))).all()
    assert row == [("kept", "")]


async def test_running_the_upgrade_twice_is_harmless(fresh_db) -> None:
    await db.init_db()
    await db.init_db()


async def test_the_api_reports_the_version(auth_client: httpx.AsyncClient, fake_adapter) -> None:
    """check() already asks /control/status for it; it used to be thrown away."""
    response = await auth_client.post(
        "/api/instances",
        json={"name": "a", "base_url": "http://a.local", "username": "admin", "password": "pw"},
    )
    assert response.status_code == 201, response.text

    body = (await auth_client.get("/api/instances")).json()
    assert body[0]["version"] == fake_adapter.VERSION
    assert body[0]["status"] == "online"


async def test_an_unreachable_instance_keeps_its_last_known_version(
    auth_client: httpx.AsyncClient, fake_adapter
) -> None:
    """Knowing what it was running last is more useful than blanking the field."""
    await auth_client.post(
        "/api/instances",
        json={"name": "a", "base_url": "http://a.local", "username": "admin", "password": "pw"},
    )
    fake_adapter.state_for("http://a.local").offline = True

    instance_id = (await auth_client.get("/api/instances")).json()[0]["id"]
    await auth_client.post(f"/api/instances/{instance_id}/test")

    body = (await auth_client.get("/api/instances")).json()[0]
    assert body["status"] == "unreachable"
    assert body["version"] == fake_adapter.VERSION


@pytest.mark.parametrize("path", ["/api/instances"])
async def test_version_is_never_a_credential(auth_client: httpx.AsyncClient, path: str) -> None:
    """Guard the shape of the instance payload while it is being changed."""
    await auth_client.post(
        "/api/instances",
        json={"name": "a", "base_url": "http://a.local", "username": "admin", "password": "pw"},
    )
    body = (await auth_client.get(path)).json()[0]
    assert "password" not in body
    assert "password_encrypted" not in body
    assert body["has_password"] is True
