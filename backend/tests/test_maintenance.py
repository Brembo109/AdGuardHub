"""Holding one node back by hand, without losing what it owes (spec §6).

Maintenance mode is not "disabled with a nicer name". A disabled instance is out
of the picture; an instance in maintenance is one the hub still owns and still
has work for — it simply keeps that work until somebody says the node is theirs
again. Every test here is about that difference.
"""

from __future__ import annotations

import httpx

from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


async def set_maintenance(client: httpx.AsyncClient, instance_id: int, value: bool) -> dict:
    response = await client.patch(f"/api/instances/{instance_id}", json={"maintenance": value})
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_node_in_maintenance_is_not_pushed_to(auth_client: httpx.AsyncClient) -> None:
    held = await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    await set_maintenance(auth_client, held, True)

    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    # The other node is unaffected — holding one back never delays the rest.
    assert FakeAdapter.state_for(B).rules == ["||ads.example.com^"]
    assert FakeAdapter.state_for(A).rules == []


async def test_what_it_missed_is_queued_rather_than_dropped(
    auth_client: httpx.AsyncClient,
) -> None:
    held = await add_instance(auth_client, "a", A)
    await set_maintenance(auth_client, held, True)

    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    jobs = (await auth_client.get("/api/jobs")).json()
    assert [job["payload_kind"] for job in jobs if job["instance_id"] == held]
    # Queued, not failed: nothing went wrong, the hub simply held it.
    assert all(job["status"] == "pending" for job in jobs if job["instance_id"] == held)


async def test_releasing_it_replays_the_queue(auth_client: httpx.AsyncClient) -> None:
    held = await add_instance(auth_client, "a", A)
    await set_maintenance(auth_client, held, True)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()
    assert FakeAdapter.state_for(A).rules == []

    await set_maintenance(auth_client, held, False)
    await drain_background()

    # The point of the whole feature: the node catches up on release rather than
    # waiting for the retry timer, and without anyone pressing sync.
    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]
    open_jobs = (await auth_client.get("/api/jobs")).json()
    assert [job for job in open_jobs if job["instance_id"] == held] == []


async def test_reconciliation_leaves_it_alone(auth_client: httpx.AsyncClient) -> None:
    held = await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    await set_maintenance(auth_client, held, True)
    # Somebody is working on the node: they remove the rule by hand.
    FakeAdapter.state_for(A).rules = []

    reports = (await auth_client.post("/api/reconcile")).json()
    report = next(item for item in reports if item["instance_id"] == held)
    assert report["checked"] is False
    assert report["differences"] == []
    # Not corrected behind their back.
    assert FakeAdapter.state_for(A).rules == []


async def test_the_status_says_maintenance_rather_than_a_fault(
    auth_client: httpx.AsyncClient,
) -> None:
    held = await add_instance(auth_client, "a", A)
    assert (await set_maintenance(auth_client, held, True))["status"] == "maintenance"
    # Released, the status is cleared rather than guessed: the probe writes the truth.
    assert (await set_maintenance(auth_client, held, False))["status"] != "maintenance"


async def test_disabling_wins_over_maintenance(auth_client: httpx.AsyncClient) -> None:
    """An instance nobody syncs at all is not "being worked on"."""
    held = await add_instance(auth_client, "a", A)
    await set_maintenance(auth_client, held, True)

    response = await auth_client.patch(f"/api/instances/{held}", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
