"""How big each subscription is — a number the hub cannot know by itself.

AdGuardHub stores subscription URLs and their enabled state, never the resolved
domain lists (spec §12), so "how many rules are in this list" has exactly one
source: the nodes that downloaded it. These tests pin down what follows from
that — the answer needs a reachable node, nodes may legitimately disagree, and
none of it is configuration the hub owns.
"""

from __future__ import annotations

import httpx

from app.adapters.base import RemoteFilterList
from app.services import filtersizes
from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance

URL = "https://lists.example.com/ads.txt"
OTHER = "https://lists.example.com/tracking.txt"


async def subscribe(client: httpx.AsyncClient, url: str, *, enabled: bool = True) -> int:
    response = await client.post(
        "/api/filter-lists", json={"name": url, "url": url, "kind": "blocklist"}
    )
    assert response.status_code == 201, response.text
    item = response.json()
    if not enabled:
        await client.patch(f"/api/filter-lists/{item['id']}", json={"enabled": False})
    # Subscribing pushes to every node; let that finish before the test says what
    # the nodes report, or the push would land on top of it.
    await drain_background()
    return int(item["id"])


def report(base_url: str, *lists: RemoteFilterList) -> None:
    """Put what a node would answer with into its fake state."""
    FakeAdapter.state_for(base_url).filter_lists = list(lists)
    filtersizes.invalidate()


def entry(url: str, count: int, *, enabled: bool = True) -> RemoteFilterList:
    return RemoteFilterList(
        name=url, url=url, enabled=enabled, kind="blocklist", rules_count=count
    )


async def sizes(client: httpx.AsyncClient) -> dict:
    response = await client.get("/api/filter-lists/sizes")
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_count_comes_from_the_node(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 54321))

    body = await sizes(auth_client)
    assert [(item["url"], item["rules_count"]) for item in body["lists"]] == [(URL, 54321)]
    assert body["total_rules"] == 54321
    assert body["instances_reporting"] == 1


async def test_only_enabled_subscriptions_count_towards_the_total(
    auth_client: httpx.AsyncClient,
) -> None:
    """A list the hub switched off is off on every node, so it filters nothing."""
    await add_instance(auth_client, "a", A)
    await subscribe(auth_client, URL)
    await subscribe(auth_client, OTHER, enabled=False)
    report(A, entry(URL, 1000), entry(OTHER, 500, enabled=False))

    body = await sizes(auth_client)
    assert body["total_rules"] == 1000
    # The size of the disabled list is still reported per row — it is a fact about
    # the file, and hiding it would make an operator wonder what they turned off.
    assert {item["url"]: item["rules_count"] for item in body["lists"]} == {URL: 1000, OTHER: 500}


async def test_nodes_that_disagree_are_reported_rather_than_averaged(
    auth_client: httpx.AsyncClient,
) -> None:
    """Refresh schedules differ; one node holding an older copy is not an error."""
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 90000))
    report(B, entry(URL, 91500))

    item = (await sizes(auth_client))["lists"][0]
    # The largest, because a node that has not fetched yet reports 0 and a stale
    # copy is smaller than a fresh one.
    assert item["rules_count"] == 91500
    assert item["agreed"] is False
    assert {entry["instance_name"]: entry["rules_count"] for entry in item["per_instance"]} == {
        "a": 90000,
        "b": 91500,
    }


async def test_agreement_is_the_normal_case(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 90000))
    report(B, entry(URL, 90000))

    item = (await sizes(auth_client))["lists"][0]
    assert item["agreed"] is True
    assert item["rules_count"] == 90000


async def test_an_unreachable_fleet_gives_no_number_rather_than_zero(
    auth_client: httpx.AsyncClient,
) -> None:
    """Zero rules and "nobody could tell us" are different things to an operator."""
    await add_instance(auth_client, "a", A)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 54321))
    FakeAdapter.state_for(A).offline = True
    filtersizes.invalidate()

    body = await sizes(auth_client)
    assert body["instances_reporting"] == 0
    assert body["instances_total"] == 1
    # The row survives with an empty breakdown, which is what the interface renders
    # as a dash instead of a count.
    assert body["lists"][0]["per_instance"] == []


async def test_a_list_the_hub_does_not_know_is_not_reported(
    auth_client: httpx.AsyncClient,
) -> None:
    """Anything extra on a node is drift for reconciliation to remove, not a row here."""
    await add_instance(auth_client, "a", A)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 100), entry("https://rogue.example.com/list.txt", 999))

    body = await sizes(auth_client)
    assert [item["url"] for item in body["lists"]] == [URL]
    assert body["total_rules"] == 100


async def test_changing_a_subscription_does_not_serve_a_stale_count(
    auth_client: httpx.AsyncClient,
) -> None:
    """The fan-out is cached for a minute; a subscription change has to drop it."""
    await add_instance(auth_client, "a", A)
    await subscribe(auth_client, URL)
    report(A, entry(URL, 100))
    assert len((await sizes(auth_client))["lists"]) == 1

    # No invalidate() here: adding the subscription is what has to drop the cache.
    await subscribe(auth_client, OTHER)

    body = await sizes(auth_client)
    assert {item["url"] for item in body["lists"]} == {URL, OTHER}
    # The new list is in the table at once but weighs nothing yet — the node has
    # not downloaded it. That is the honest state, not a missing row.
    assert body["total_rules"] == 100


async def test_sizes_need_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/filter-lists/sizes")).status_code == 401
