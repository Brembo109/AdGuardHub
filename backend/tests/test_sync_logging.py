"""What the hub says about its own syncing.

Before this, the sync core wrote three log statements in total and all three
fired only when a whole pass crashed. A push that failed for one instance, a
node going unreachable, a correction that did not hold — none of it reached the
log. It went to the database, and the database holds state per object, not the
order things happened in. "What happened at 08:25" had no answer.

These tests pin the lines an operator would go looking for, and — just as much —
the silence on the paths that run on a timer. Two nodes reconciled every five
minutes would write 576 lines a day to say nothing happened.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, add_instance


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="app.services")
    return caplog


def lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [item.getMessage() for item in caplog.records if item.levelno == level]


async def test_a_push_that_landed_is_recorded(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    instance_id = await add_instance(auth_client, "a", A)
    records.clear()
    await auth_client.post(f"/api/instances/{instance_id}/push")

    assert any("Pushed" in line and "a" in line for line in lines(records, logging.INFO))


async def test_a_failed_push_says_so_and_says_it_was_queued(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    """It was notified and stored, and the log — where you look first — was silent."""
    instance_id = await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).offline = True
    records.clear()
    await auth_client.post(f"/api/instances/{instance_id}/push")

    warnings = lines(records, logging.WARNING)
    assert any("Push to a failed" in line for line in warnings)
    assert any("queued for retry" in line for line in warnings)


async def test_a_refused_push_is_warned_about_by_name(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    instance_id = await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).refuses = {"@@||hitmyl.ink^"}
    await auth_client.post("/api/rules/allow", json={"domain": "hitmyl.ink"})
    await drain_background()
    records.clear()
    await auth_client.post(f"/api/instances/{instance_id}/push")

    assert any("@@||hitmyl.ink^" in line for line in lines(records, logging.WARNING))


async def test_going_unreachable_is_logged_once_rather_than_every_pass(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    """A node down for an hour must not write the same warning twelve times."""
    instance_id = await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).offline = True
    records.clear()

    for _ in range(3):
        await auth_client.post(f"/api/instances/{instance_id}/test")

    assert len([line for line in lines(records, logging.WARNING) if "unreachable" in line]) == 1


async def test_coming_back_is_logged(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    instance_id = await add_instance(auth_client, "a", A)
    FakeAdapter.state_for(A).offline = True
    await auth_client.post(f"/api/instances/{instance_id}/test")

    FakeAdapter.state_for(A).offline = False
    records.clear()
    await auth_client.post(f"/api/instances/{instance_id}/test")

    assert any("answered again" in line for line in lines(records, logging.INFO))


async def test_a_reconcile_that_found_something_says_what(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()
    FakeAdapter.state_for(A).rules = []
    records.clear()

    await auth_client.post("/api/reconcile")

    assert any(
        "Reconcile a" in line and "corrected" in line for line in lines(records, logging.INFO)
    )


async def test_a_quiet_reconcile_stays_out_of_the_log(
    auth_client: httpx.AsyncClient, records: pytest.LogCaptureFixture
) -> None:
    """The half that matters as much as the other: this runs on a timer."""
    await add_instance(auth_client, "a", A)
    await auth_client.post("/api/rules", json={"text": "||ads.example.com^"})
    await drain_background()
    records.clear()

    await auth_client.post("/api/reconcile")

    assert [line for line in lines(records, logging.INFO) if "Reconcile" in line] == []
