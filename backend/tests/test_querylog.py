"""Aggregated query log (spec §9) and the initial import (spec §7)."""

from __future__ import annotations

import httpx

from app.adapters.base import QueryLogEntry, RemoteFilterList
from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


def entry(host: str, when: str, *, blocked: bool = True) -> QueryLogEntry:
    return QueryLogEntry(
        time=when,
        question=host,
        question_type="A",
        client="192.168.1.10",
        answer_status="FilteredBlackList" if blocked else "NotFilteredNotFound",
        blocked=blocked,
        rule="||ads.example.com^" if blocked else "",
    )


async def test_log_is_merged_across_instances_and_tagged(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    FakeAdapter.state_for(A).query_log = [entry("ads.example.com", "2026-01-01T10:00:00Z")]
    FakeAdapter.state_for(B).query_log = [
        entry("cdn.example.com", "2026-01-01T10:00:05Z", blocked=False)
    ]

    assert (await auth_client.post("/api/querylog/refresh")).json()["new_entries"] == 2

    rows = (await auth_client.get("/api/querylog")).json()
    assert [row["instance"] for row in rows] == ["b", "a"]  # newest first
    assert rows[1]["question"] == "ads.example.com"


async def test_repeated_polls_do_not_duplicate_entries(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).query_log = [entry("ads.example.com", "2026-01-01T10:00:00Z")]

    await auth_client.post("/api/querylog/refresh")
    assert (await auth_client.post("/api/querylog/refresh")).json()["new_entries"] == 0
    assert len((await auth_client.get("/api/querylog")).json()) == 1


async def test_log_filters(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).query_log = [
        entry("ads.example.com", "2026-01-01T10:00:00Z"),
        entry("safe.example.com", "2026-01-01T10:00:01Z", blocked=False),
    ]
    await auth_client.post("/api/querylog/refresh")

    assert len((await auth_client.get("/api/querylog?blocked_only=true")).json()) == 1
    assert len((await auth_client.get("/api/querylog?search=safe")).json()) == 1
    assert len((await auth_client.get("/api/querylog?instance=nope")).json()) == 0


async def test_unreachable_instance_does_not_break_the_aggregate(
    auth_client: httpx.AsyncClient,
) -> None:
    await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    FakeAdapter.state_for(A).query_log = [entry("ads.example.com", "2026-01-01T10:00:00Z")]
    FakeAdapter.state_for(B).offline = True

    assert (await auth_client.post("/api/querylog/refresh")).json()["new_entries"] == 1


async def test_import_adopts_master_state_and_overwrites_the_rest(
    auth_client: httpx.AsyncClient,
) -> None:
    master = await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)

    FakeAdapter.state_for(A).rules = [
        "! why these two exist",
        "",
        "||ads.example.com^",
        "@@||shop.example.com^",
    ]
    FakeAdapter.state_for(A).filter_lists = [
        RemoteFilterList("AdGuard DNS filter", "https://example.com/list.txt", True, "blocklist")
    ]
    FakeAdapter.state_for(B).rules = ["||stale-rule-from-b.com^"]

    result = (await auth_client.post(f"/api/instances/{master}/import", json={})).json()
    # The comment is adopted like any other line; only the blank one is dropped.
    assert result["rules_imported"] == 3
    assert result["rules_skipped"] == 1
    assert result["filter_lists_imported"] == 1
    await drain_background()

    rules = sorted(rule["text"] for rule in (await auth_client.get("/api/rules")).json())
    assert rules == ["! why these two exist", "@@||shop.example.com^", "||ads.example.com^"]

    # B's pre-existing state is overwritten, not merged (spec §7) — and it arrives
    # in the master's original order, comment included, since a comment above the
    # wrong rule explains nothing.
    assert FakeAdapter.state_for(B).rules == [
        "! why these two exist",
        "||ads.example.com^",
        "@@||shop.example.com^",
    ]
    assert "||stale-rule-from-b.com^" not in FakeAdapter.state_for(B).rules
