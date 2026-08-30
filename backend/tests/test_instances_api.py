"""Instance editing and the pre-save connection check."""

from __future__ import annotations

import httpx

from app.adapters import session as adapter_session

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


async def test_connection_check_before_saving(auth_client: httpx.AsyncClient) -> None:
    ok = await auth_client.post(
        "/api/instances/test-connection",
        json={"base_url": A, "username": "admin", "password": "pw"},
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["version"] == "v0.107.fake"

    # Nothing was saved by testing.
    assert (await auth_client.get("/api/instances")).json() == []


async def test_failed_connection_check_reports_inline(auth_client: httpx.AsyncClient) -> None:
    FakeAdapter.state_for(B).offline = True
    response = await auth_client.post(
        "/api/instances/test-connection",
        json={"base_url": B, "username": "admin", "password": "pw"},
    )
    # A failure is a result, not an exception: the form shows it next to the field.
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "unreachable" in response.json()["error"]


async def test_connection_check_reuses_the_stored_password(
    auth_client: httpx.AsyncClient,
) -> None:
    """Editing an instance must not force the operator to retype the password."""
    instance_id = await add_instance(auth_client, "a", A)
    response = await auth_client.post(
        "/api/instances/test-connection",
        json={"base_url": A, "username": "admin", "password": "", "instance_id": instance_id},
    )
    assert response.json()["ok"] is True


async def test_editing_an_instance(auth_client: httpx.AsyncClient) -> None:
    instance_id = await add_instance(auth_client, "a", A)

    updated = await auth_client.patch(
        f"/api/instances/{instance_id}",
        json={"name": "adguard-primary", "base_url": B, "username": "root"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "adguard-primary"
    assert body["base_url"] == B
    assert body["username"] == "root"
    # An omitted password leaves the stored one alone.
    assert body["has_password"] is True


async def test_editing_clears_the_cached_session(auth_client: httpx.AsyncClient) -> None:
    """A cookie for the old URL/user must not survive an edit."""
    instance_id = await add_instance(auth_client, "a", A)
    adapter_session.store.set(("http://adguard-a.local", "admin"), httpx.Cookies())
    assert adapter_session.store.get(("http://adguard-a.local", "admin")) is not None

    await auth_client.patch(f"/api/instances/{instance_id}", json={"username": "root"})
    assert adapter_session.store.get(("http://adguard-a.local", "admin")) is None


async def test_duplicate_name_is_rejected_on_edit(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    second = await add_instance(auth_client, "b", B)

    response = await auth_client.patch(f"/api/instances/{second}", json={"name": "a"})
    assert response.status_code == 409


async def test_connection_check_rejects_a_bad_url(auth_client: httpx.AsyncClient) -> None:
    response = await auth_client.post(
        "/api/instances/test-connection", json={"base_url": "adguard.local"}
    )
    assert response.status_code == 422
