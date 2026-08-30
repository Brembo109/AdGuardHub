"""The core promise: one change in the hub reaches every instance (spec §2, §6)."""

from __future__ import annotations

import httpx

from app.services.sync import drain_background

from .fakes import FakeAdapter

A = "http://adguard-a.local"
B = "http://adguard-b.local"


async def add_instance(client: httpx.AsyncClient, name: str, url: str) -> int:
    response = await client.post(
        "/api/instances",
        json={"name": name, "base_url": url, "username": "admin", "password": "pw"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_credentials_are_encrypted_and_never_returned(
    auth_client: httpx.AsyncClient,
) -> None:
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import Instance

    await add_instance(auth_client, "a", A)
    body = (await auth_client.get("/api/instances")).json()[0]
    assert "password" not in body
    assert body["has_password"] is True

    async with session_scope() as session:
        instance = (await session.execute(select(Instance))).scalars().one()
    assert instance.password_encrypted != "pw"
    assert "pw" not in instance.password_encrypted


async def test_rule_is_pushed_to_every_instance(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)

    created = await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    assert created.status_code == 201
    await drain_background()

    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]
    assert FakeAdapter.state_for(B).rules == ["||ads.example.com^"]


async def test_whitelisting_from_the_query_log_reaches_both_instances(
    auth_client: httpx.AsyncClient,
) -> None:
    """The failover race this project exists to fix: B must get A's whitelist too."""
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)

    response = await auth_client.post("/api/rules/allow", json={"domain": "Tracking.Example.COM."})
    assert response.status_code == 200
    assert response.json()["text"] == "@@||tracking.example.com^"
    assert response.json()["kind"] == "allow"
    await drain_background()

    for url in (A, B):
        assert FakeAdapter.state_for(url).rules == ["@@||tracking.example.com^"]


async def test_unreachable_instance_does_not_block_the_others(
    auth_client: httpx.AsyncClient,
) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    FakeAdapter.state_for(B).offline = True

    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    # A still got the change immediately — no rollback, no waiting (spec §6).
    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]
    assert FakeAdapter.state_for(B).rules == []

    jobs = (await auth_client.get("/api/jobs")).json()
    assert [job["instance_name"] for job in jobs] == ["b"]
    assert jobs[0]["status"] == "failed"

    instances = {item["name"]: item for item in (await auth_client.get("/api/instances")).json()}
    assert instances["b"]["status"] == "unreachable"

    # Once B is back, the retry queue applies the full current state.
    FakeAdapter.state_for(B).offline = False
    retried = await auth_client.post("/api/jobs/retry")
    assert retried.json() == {"recovered": 1}
    assert FakeAdapter.state_for(B).rules == ["||ads.example.com^"]
    assert (await auth_client.get("/api/jobs")).json() == []


async def test_disabled_instances_are_skipped(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    instance_b = await add_instance(auth_client, "b", B)
    await auth_client.patch(f"/api/instances/{instance_b}", json={"enabled": False})

    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]
    assert FakeAdapter.state_for(B).rules == []
    assert (await auth_client.get("/api/jobs")).json() == []


async def test_disabled_rules_are_not_pushed(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    created = await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()
    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]

    await auth_client.patch(f"/api/rules/{created.json()['id']}", json={"enabled": False})
    await drain_background()
    assert FakeAdapter.state_for(A).rules == []


async def test_filter_list_subscriptions_are_pushed(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    response = await auth_client.post(
        "/api/filter-lists",
        json={"name": "AdGuard DNS filter", "url": "https://example.com/list.txt"},
    )
    assert response.status_code == 201
    await drain_background()

    lists = FakeAdapter.state_for(A).filter_lists
    assert [(item.url, item.kind, item.enabled) for item in lists] == [
        ("https://example.com/list.txt", "blocklist", True)
    ]

    await auth_client.patch(f"/api/filter-lists/{response.json()['id']}", json={"enabled": False})
    await drain_background()
    assert FakeAdapter.state_for(A).filter_lists[0].enabled is False


async def test_dns_settings_only_pushed_when_managed(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)

    await auth_client.put("/api/settings/dns", json={"managed": False, "upstream_dns": "1.1.1.1"})
    await auth_client.post("/api/sync")
    assert FakeAdapter.state_for(A).dns == {}

    await auth_client.put(
        "/api/settings/dns",
        json={"managed": True, "upstream_dns": "1.1.1.1\n9.9.9.9", "dnssec_enabled": True},
    )
    await drain_background()
    assert FakeAdapter.state_for(A).dns["upstream_dns"] == ["1.1.1.1", "9.9.9.9"]
    assert FakeAdapter.state_for(A).dns["dnssec_enabled"] is True


async def test_manual_full_sync_reports_failures(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    FakeAdapter.state_for(B).offline = True

    result = (await auth_client.post("/api/sync")).json()
    assert result["instances"] == 2
    assert list(result["failed"]) == ["b"]
