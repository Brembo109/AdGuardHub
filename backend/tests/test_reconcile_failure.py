"""When a correction cannot be pushed at all.

There are three ways a reconciliation pass can end for one payload kind, and
until now two of them looked identical to the operator. The node kept the
correction; the node took it and did not keep it; or the push itself errored and
the node never saw it. Only the middle one said so — the third arrived in the
drift log as the bare word *detected*, five minutes apart, for as long as the
fault lasted, with the reason sitting in a field nothing persists.

The second half of this is the shared `try` that used to wrap the whole loop: a
settings section one AdGuard build rejects aborted the pass, so the rule set was
never corrected either, and nothing in the log said which of the two had
happened.
"""

from __future__ import annotations

import httpx

from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, add_instance


async def _drift_rows(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get("/api/drift")
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_push_that_errors_says_so_instead_of_just_detected(
    auth_client: httpx.AsyncClient,
) -> None:
    await add_instance(auth_client, "node-a", A)
    await auth_client.post("/api/rules", json={"text": "@@||example.test^", "kind": "allow"})
    await drain_background()

    state = FakeAdapter.state_for(A)
    # The node answers reads, so it is online and the difference is real — it
    # just will not take the write.
    state.rules = []
    state.push_errors.add("rules")

    reports = (await auth_client.post("/api/reconcile")).json()

    assert reports[0]["corrected"] is False
    assert "rejected the rules push" in reports[0]["error"]

    row = (await _drift_rows(auth_client))[0]
    assert row["corrected"] is False
    # Both halves: what differs, and why it is still differing.
    assert "1 rule(s) missing" in row["summary"]
    assert "the correction could not be pushed" in row["summary"]
    assert "rejected the rules push" in row["summary"]


async def test_one_failing_payload_no_longer_blocks_the_others(
    auth_client: httpx.AsyncClient,
) -> None:
    """The bug behind the bug.

    Settings are checked after rules, but the shared try block meant an error on
    *either* ended the pass. A node whose settings push fails must still get its
    rule set corrected — best effort with no rollback is the rule everywhere
    else in the sync engine.
    """
    await add_instance(auth_client, "node-a", A)
    await auth_client.post("/api/rules", json={"text": "@@||example.test^", "kind": "allow"})
    await auth_client.patch(
        "/api/config/sections/filtering_config",
        json={"managed": True, "data": {"enabled": True, "interval": 24}},
    )
    await drain_background()

    state = FakeAdapter.state_for(A)
    state.rules = []
    # Present but wrong, not absent: an absent section reads as "this AdGuard
    # build does not implement the area", which is a capability gap rather than
    # drift and is deliberately not corrected.
    state.sections["filtering_config"] = {"enabled": False, "interval": 24}
    state.push_errors.add("settings")

    await auth_client.post("/api/reconcile")

    # The rule set landed even though the settings push threw.
    assert state.rules == ["@@||example.test^"]

    rows = {row["payload_kind"]: row for row in await _drift_rows(auth_client)}
    assert rows["rules"]["corrected"] is True
    assert rows["settings"]["corrected"] is False
    assert "could not be pushed" in rows["settings"]["summary"]


async def test_the_same_failure_is_stated_once_not_on_every_pass(
    auth_client: httpx.AsyncClient,
) -> None:
    """A push that errors errors again five minutes later, by definition.

    Same reasoning as a refusal: say it once, say it again when it changes. The
    alternative is several hundred identical rows a day, which is how a log
    stops being read.
    """
    await add_instance(auth_client, "node-a", A)
    await auth_client.post("/api/rules", json={"text": "@@||example.test^", "kind": "allow"})
    await drain_background()

    state = FakeAdapter.state_for(A)
    state.rules = []
    state.push_errors.add("rules")

    for _ in range(3):
        await auth_client.post("/api/reconcile")

    rows = await _drift_rows(auth_client)
    assert len([row for row in rows if "could not be pushed" in row["summary"]]) == 1


async def test_recovery_is_reported_again(auth_client: httpx.AsyncClient) -> None:
    """Silence while a fault repeats must not outlive the fault."""
    await add_instance(auth_client, "node-a", A)
    await auth_client.post("/api/rules", json={"text": "@@||example.test^", "kind": "allow"})
    await drain_background()

    state = FakeAdapter.state_for(A)
    state.rules = []
    state.push_errors.add("rules")
    await auth_client.post("/api/reconcile")

    state.push_errors.discard("rules")
    await auth_client.post("/api/reconcile")

    assert state.rules == ["@@||example.test^"]
    rows = await _drift_rows(auth_client)
    assert rows[0]["corrected"] is True
    assert "could not be pushed" not in rows[0]["summary"]
