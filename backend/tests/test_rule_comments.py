"""Comment lines in a rule set, and why losing them was worse than it sounds.

A `!` line is where an operator writes down *why* a rule exists — "allowed after
the doorbell app broke", "blocks the TV's telemetry, do not remove". The hub
dropped those on import and then, because it is the source of truth for the whole
rule set, reconciliation removed them from the node as unexpected.

So the failure was not "comments are not supported". It was: connect the hub, and
within one reconciliation pass the notes you had written in AdGuard are gone from
every node, with nothing said about it. That is the property these tests pin.
"""

from __future__ import annotations

import httpx
import pytest

from app.db import session_scope
from app.models import Instance
from app.services import reconcile as reconcile_module
from app.services.rules import classify

from .fakes import FakeAdapter
from .test_sync import A, add_instance


def test_a_comment_is_classified_as_one() -> None:
    assert classify("! a note").value == "comment"
    assert classify("# a note").value == "comment"
    assert classify("  ! indented").value == "comment"


def test_a_commented_out_rule_stays_a_comment() -> None:
    """`@@` inside a comment is text, not an exception rule."""
    assert classify("! @@||example.com^").value == "comment"
    assert classify("# ||ads.example.com^").value == "comment"


def test_real_rules_are_unaffected() -> None:
    assert classify("@@||shop.example.com^").value == "allow"
    assert classify("||ads.example.com^").value == "block"


@pytest.mark.usefixtures("fresh_db", "fake_adapter")
async def test_reconciliation_no_longer_strips_comments_from_a_node(
    auth_client: httpx.AsyncClient,
) -> None:
    """The failure this whole change exists for.

    Import a node whose rules carry notes, then let reconciliation run. It used to
    find the comments "unexpected" — they were never stored — and delete them.
    """
    master = await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).rules = [
        "! blocks the TV's telemetry, do not remove",
        "||telemetry.example.com^",
        "! allowed after the doorbell app broke",
        "@@||api.ring.com^",
    ]

    await auth_client.post(f"/api/instances/{master}/import", json={})

    async with session_scope() as session:
        report = await reconcile_module.reconcile_instance(
            session, await session.get(Instance, master)
        )

    assert report.differences == [], f"reconciliation wanted to change something: {report}"
    assert FakeAdapter.state_for(A).rules == [
        "! blocks the TV's telemetry, do not remove",
        "||telemetry.example.com^",
        "! allowed after the doorbell app broke",
        "@@||api.ring.com^",
    ]


@pytest.mark.usefixtures("fresh_db", "fake_adapter")
async def test_a_comment_can_be_deleted_like_any_other_line(
    auth_client: httpx.AsyncClient,
) -> None:
    """Preserved is not the same as stuck: the operator still owns the rule set."""
    created = await auth_client.post("/api/rules", json={"text": "! temporary note"})
    rule_id = created.json()["id"]
    assert (await auth_client.delete(f"/api/rules/{rule_id}")).status_code == 204
    assert (await auth_client.get("/api/rules")).json() == []


@pytest.mark.usefixtures("fresh_db", "fake_adapter")
async def test_comments_can_be_filtered_out_of_the_list(
    auth_client: httpx.AsyncClient,
) -> None:
    """The Block and Allow tabs must still show rules only."""
    await auth_client.post(
        "/api/rules/bulk", json={"text": "! note\n||ads.example.com^\n@@||shop.example.com^"}
    )
    kinds = {
        kind: [r["text"] for r in (await auth_client.get(f"/api/rules?kind={kind}")).json()]
        for kind in ("block", "allow", "comment")
    }
    assert kinds["block"] == ["||ads.example.com^"]
    assert kinds["allow"] == ["@@||shop.example.com^"]
    assert kinds["comment"] == ["! note"]
