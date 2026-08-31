"""Drift detection and correction (spec §6)."""

from __future__ import annotations

import httpx

from app.adapters.base import AdapterError, RemoteFilterList
from app.services.reconcile import diff_filter_lists, diff_rules, diff_settings
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


def test_diff_settings_is_quiet_when_nothing_is_managed() -> None:
    assert diff_settings({}, {}) is None


def test_diff_settings_reports_the_changed_keys_per_section() -> None:
    difference = diff_settings(
        {"dns": {"upstream_dns": ["1.1.1.1"], "dnssec_enabled": True}},
        {"dns": {"upstream_dns": ["8.8.8.8"], "dnssec_enabled": True}},
    )
    assert difference is not None
    assert difference.details["dns"]["upstream_dns"]["actual"] == ["8.8.8.8"]
    # An unchanged key must not be reported as drift.
    assert "dnssec_enabled" not in difference.details["dns"]


def test_diff_settings_flags_an_unsupported_section_without_calling_it_drift() -> None:
    """An instance that lacks an area is a capability gap, not a config difference."""
    difference = diff_settings({"tls": {"enabled": True}}, {"tls": None})
    assert difference is not None
    assert difference.details["_unsupported"] == ["tls"]
    assert "not supported" in difference.summary


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


async def test_a_capability_gap_is_not_logged_as_drift(auth_client: httpx.AsyncClient) -> None:
    """An area the instance does not implement must not append drift on every run.

    Reconciliation runs on a timer, so logging a standing capability gap would grow
    the drift log forever and drown the real findings.
    """
    await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).unsupported_sections = {"tls"}
    await auth_client.patch(
        "/api/config/sections/tls", json={"managed": True, "data": {"enabled": True}}
    )
    await drain_background()

    for _ in range(3):
        reports = (await auth_client.post("/api/reconcile")).json()

    # It is still reported to the caller…
    assert "not supported" in reports[0]["differences"][0]["summary"]
    # …but never written to the log.
    assert (await auth_client.get("/api/drift")).json() == []


async def test_drift_is_reported_even_when_the_correction_fails(
    auth_client: httpx.AsyncClient,
) -> None:
    """The dashboard summary reads `differences`, so a failed fix must not look clean."""
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()

    FakeAdapter.state_for(A).rules = ["||rogue.example^"]
    # The instance drops off between the read and the write.
    original_push = FakeAdapter.push_rules

    async def failing_push(self, rules):
        raise AdapterError("connection reset")

    FakeAdapter.push_rules = failing_push
    try:
        reports = (await auth_client.post("/api/reconcile")).json()
    finally:
        FakeAdapter.push_rules = original_push

    assert reports[0]["checked"] is True
    assert reports[0]["corrected"] is False
    assert len(reports[0]["differences"]) == 1
    assert "connection reset" in reports[0]["error"]

    # Logged as found-but-not-fixed, rather than silently dropped or marked corrected.
    drift = (await auth_client.get("/api/drift")).json()
    assert len(drift) == 1
    assert drift[0]["corrected"] is False


async def test_each_difference_records_its_own_outcome(
    auth_client: httpx.AsyncClient,
) -> None:
    """Rules can land while settings fail; one aggregate flag would mislabel both."""
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await auth_client.patch(
        "/api/config/sections/dns", json={"managed": True, "data": {"upstream_dns": ["1.1.1.1"]}}
    )
    await drain_background()

    state = FakeAdapter.state_for(A)
    state.rules = []
    state.sections["dns"] = {"upstream_dns": ["8.8.8.8"]}

    async def failing_section(self, name, data):
        raise AdapterError("section rejected")

    original = FakeAdapter.push_section
    FakeAdapter.push_section = failing_section
    try:
        await auth_client.post("/api/reconcile")
    finally:
        FakeAdapter.push_section = original

    outcomes = {
        event["payload_kind"]: event["corrected"]
        for event in (await auth_client.get("/api/drift")).json()
    }
    assert outcomes == {"rules": True, "settings": False}
