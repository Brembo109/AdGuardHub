"""The dashboard's own statistics endpoint, and the cache that protects the nodes.

Collecting statistics fans out to every instance. A dashboard left open in two tabs
must not turn into a load generator on the resolvers it is supposed to be watching.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import aggregate

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


async def _seed(client: httpx.AsyncClient) -> None:
    await add_instance(client, "a", A)
    await add_instance(client, "b", B)
    FakeAdapter.state_for(A).stats = {
        "num_dns_queries": 100,
        "num_blocked_filtering": 25,
        "num_replaced_safebrowsing": 2,
        "dns_queries": [1, 2, 3],
        "blocked_filtering": [1, 0, 1],
        "top_queried_domains": [{"example.com": 40}],
        "top_blocked_domains": [{"ads.example.com": 20}],
        "top_clients": [{"192.168.1.5": 70}],
    }
    FakeAdapter.state_for(B).stats = {
        "num_dns_queries": 300,
        "num_blocked_filtering": 75,
        "dns_queries": [4, 5, 6],
        "blocked_filtering": [2, 1, 0],
        "top_queried_domains": [{"example.com": 60}],
        "top_clients": [{"192.168.1.5": 30}, {"192.168.1.9": 10}],
    }


async def test_traffic_sums_every_node(auth_client: httpx.AsyncClient) -> None:
    await _seed(auth_client)

    body = (await auth_client.get("/api/traffic")).json()

    assert body["queries"] == 400
    assert body["blocked"] == 100
    assert body["block_rate"] == pytest.approx(25.0)
    assert body["series_queries"] == [5, 7, 9]
    assert body["series_blocked"] == [3, 1, 1]
    assert body["top_queried"][0] == {"name": "example.com", "count": 100}
    assert body["top_clients"][0] == {"name": "192.168.1.5", "count": 100}
    assert body["instances_reporting"] == 2
    assert body["instances_total"] == 2


async def test_a_silent_node_is_named_rather_than_hidden(auth_client: httpx.AsyncClient) -> None:
    """A total short by one node reads as a quiet day unless the page says otherwise."""
    await _seed(auth_client)
    FakeAdapter.state_for(B).offline = True
    aggregate.invalidate_stats_cache()

    body = (await auth_client.get("/api/traffic")).json()

    assert body["queries"] == 100
    assert body["instances_reporting"] == 1
    assert body["instances_total"] == 2


async def test_repeated_reads_do_not_re_poll_the_nodes(auth_client: httpx.AsyncClient) -> None:
    await _seed(auth_client)
    FakeAdapter.state_for(A).stats_calls = 0

    for _ in range(5):
        assert (await auth_client.get("/api/traffic")).status_code == 200

    assert FakeAdapter.state_for(A).stats_calls == 1


async def test_concurrent_readers_collapse_into_one_fan_out(
    auth_client: httpx.AsyncClient,
) -> None:
    """Without the lock, three tabs opening at once would each start their own poll."""
    await _seed(auth_client)
    FakeAdapter.state_for(A).stats_calls = 0

    await asyncio.gather(*(auth_client.get("/api/traffic") for _ in range(3)))

    assert FakeAdapter.state_for(A).stats_calls == 1


async def test_the_cache_expires(auth_client: httpx.AsyncClient, monkeypatch) -> None:
    await _seed(auth_client)
    monkeypatch.setattr(aggregate, "STATS_CACHE_TTL", 0.0)
    FakeAdapter.state_for(A).stats_calls = 0

    await auth_client.get("/api/traffic")
    await auth_client.get("/api/traffic")

    assert FakeAdapter.state_for(A).stats_calls == 2


async def test_removing_an_instance_drops_the_held_numbers(
    auth_client: httpx.AsyncClient,
) -> None:
    await _seed(auth_client)
    assert (await auth_client.get("/api/traffic")).json()["queries"] == 400

    instances = (await auth_client.get("/api/instances")).json()
    b = next(item for item in instances if item["name"] == "b")
    await auth_client.delete(f"/api/instances/{b['id']}")

    body = (await auth_client.get("/api/traffic")).json()
    assert body["queries"] == 100
    assert body["instances_total"] == 1


async def test_traffic_needs_a_session(client: httpx.AsyncClient) -> None:
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    assert (await client.get("/api/traffic")).status_code == 401
