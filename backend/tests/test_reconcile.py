"""Drift detection and correction (spec §6)."""

from __future__ import annotations

import httpx

from app.adapters.base import RemoteFilterList
from app.services.reconcile import diff_dns, diff_filter_lists, diff_rules
from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, add_instance


def test_diff_rules_detects_both_directions() -> None:
    difference = diff_rules(["@@||a.com^", "||b.com^"], ["||b.com^", "||rogue.com^"])
    assert difference is not None
    assert difference.details["missing"] == ["@@||a.com^"]
    assert difference.details["extra"] == ["||rogue.com^"]


def test_diff_rules_is_quiet_when_states_match() -> None:
    assert diff_rules(["||a.com^"], ["||a.com^"]) is None


def test_diff_filter_lists_notices_a_disabled_subscription() -> None:
    expected = [RemoteFilterList("List", "https://e.com/l.txt", True, "blocklist")]
    actual = [RemoteFilterList("List", "https://e.com/l.txt", False, "blocklist")]
    difference = diff_filter_lists(expected, actual)
    assert difference is not None
    assert difference.details["changed"] == ["blocklist:https://e.com/l.txt"]


def test_diff_dns_ignores_unmanaged_settings() -> None:
    assert diff_dns(None, {"upstream_dns": ["8.8.8.8"]}) is None
    difference = diff_dns({"upstream_dns": ["1.1.1.1"]}, {"upstream_dns": ["8.8.8.8"]})
    assert difference is not None
    assert difference.details["upstream_dns"]["actual"] == ["8.8.8.8"]


async def test_out_of_band_change_is_corrected_and_logged(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    # Someone edits the instance directly in the native UI, despite spec §2.
    FakeAdapter.state_for(A).rules = ["||something-else.com^"]

    reports = (await auth_client.post("/api/reconcile")).json()
    assert reports[0]["corrected"] is True
    assert FakeAdapter.state_for(A).rules == ["||ads.example.com^"]

    drift = (await auth_client.get("/api/drift")).json()
    assert len(drift) == 1
    assert drift[0]["instance_name"] == "a"
    assert drift[0]["payload_kind"] == "rules"
    assert drift[0]["corrected"] is True


async def test_dry_run_reports_without_correcting(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()
    FakeAdapter.state_for(A).rules = []

    reports = (await auth_client.post("/api/reconcile?apply_fixes=false")).json()
    assert reports[0]["corrected"] is False
    assert len(reports[0]["differences"]) == 1
    assert FakeAdapter.state_for(A).rules == []

    # Detection without correction is still logged, never silent.
    assert (await auth_client.get("/api/drift")).json()[0]["corrected"] is False


async def test_reconcile_records_an_unreachable_instance(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).offline = True

    reports = (await auth_client.post("/api/reconcile")).json()
    assert reports[0]["checked"] is False
    assert "unreachable" in reports[0]["error"]
    assert (await auth_client.get("/api/drift")).json() == []


async def test_reconcile_finds_nothing_when_in_sync(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    reports = (await auth_client.post("/api/reconcile")).json()
    assert reports[0]["differences"] == []
    assert reports[0]["corrected"] is False
