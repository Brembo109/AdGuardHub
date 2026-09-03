"""What a node says about its own version, and the three answers it can give.

An AdGuard Home node can tell the hub that a newer build exists, that it is
current, or nothing at all — its own update check can be switched off in its
configuration, and older builds have no such endpoint. Those are three states,
not two, and the one that matters is that "the hub could not find out" is never
shown as "up to date". Telling an operator their DNS is current when nobody
actually asked is the one failure this feature could have.
"""

from __future__ import annotations

import httpx

from app.adapters.adguard import AdGuardAdapter
from app.adapters.base import RemoteUpdate


def adapter_answering(handler) -> AdGuardAdapter:
    """An AdGuard adapter whose transport is a function, not a node."""
    adapter = AdGuardAdapter("http://node.test", "admin", "pw")
    adapter._client = httpx.AsyncClient(  # noqa: SLF001
        base_url="http://node.test",
        transport=httpx.MockTransport(handler),
    )
    # The adapter logs in lazily; this stands in for having done so.
    adapter._authenticated = True  # noqa: SLF001
    return adapter


def json_route(payload: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, request=request)

    return handler


# --------------------------------------------------------------------------
# The three answers
# --------------------------------------------------------------------------


async def test_a_newer_build_is_reported_with_where_to_read_about_it() -> None:
    adapter = adapter_answering(
        json_route(
            {
                "current_version": "v0.107.60",
                "new_version": "v0.107.64",
                "announcement_url": "https://github.com/AdguardTeam/AdGuardHome/releases",
            }
        )
    )
    update = await adapter.check_update()
    assert update.available is True
    assert update.latest == "v0.107.64"
    assert update.url.endswith("/releases")
    assert update.error == ""


async def test_a_current_node_reports_nothing_to_install() -> None:
    """AdGuard leaves new_version out when there is none."""
    adapter = adapter_answering(json_route({"current_version": "v0.107.64"}))
    update = await adapter.check_update()
    assert update.available is False
    assert update.latest == ""
    assert update.error == ""


async def test_a_node_that_echoes_its_own_version_is_not_an_update() -> None:
    """Guards the case where a future build fills new_version unconditionally."""
    adapter = adapter_answering(
        json_route({"current_version": "v0.107.64", "new_version": "v0.107.64"})
    )
    assert (await adapter.check_update()).available is False


async def test_the_running_version_comes_from_the_caller_when_adguard_omits_it() -> None:
    """Reported from a real fleet: "v0.107.79 — update to v0.107.79".

    AdGuard's version.json carries no current_version at all. Comparing against
    that absent field meant every node whose answer named a version was reported
    as having an update to the version it was already running. The hub asks each
    node its version moments earlier, and that is what the question is now put
    against.
    """
    adapter = adapter_answering(json_route({"new_version": "v0.107.79"}))
    assert (await adapter.check_update("v0.107.79")).available is False
    # And a genuinely older node still hears about it.
    assert (await adapter.check_update("v0.107.60")).available is True


async def test_the_leading_v_is_not_a_version_difference() -> None:
    """/control/status answers v0.107.79; elsewhere the same API drops the v."""
    adapter = adapter_answering(json_route({"new_version": "v0.107.79"}))
    assert (await adapter.check_update("0.107.79")).available is False

    bare = adapter_answering(json_route({"new_version": "0.107.79"}))
    assert (await bare.check_update("v0.107.79")).available is False


async def test_a_version_nobody_can_name_is_unknown_rather_than_available() -> None:
    """With no version to compare against, "there is an update" is a guess."""
    adapter = adapter_answering(json_route({"new_version": "v0.107.79"}))
    update = await adapter.check_update()
    assert update.available is False
    assert update.error != ""


async def test_what_the_node_says_about_itself_wins() -> None:
    """A build that does send current_version is believed over the hub's copy."""
    adapter = adapter_answering(
        json_route({"current_version": "v0.107.79", "new_version": "v0.107.79"})
    )
    assert (await adapter.check_update("v0.100.0")).available is False


async def test_a_node_with_its_check_switched_off_says_so(fresh_db) -> None:
    """Not "up to date" — nobody asked. The distinction is the whole point."""
    adapter = adapter_answering(json_route({"disabled": True}))
    update = await adapter.check_update()
    assert update.available is False
    assert "switched off" in update.error


async def test_a_build_without_the_endpoint_is_reported_rather_than_assumed() -> None:
    adapter = adapter_answering(json_route({"message": "Not Found"}, status=404))
    update = await adapter.check_update()
    assert update.available is False
    assert update.error, "a 404 must leave a reason, not look like 'current'"


async def test_a_non_json_answer_does_not_take_the_reconcile_run_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>", request=request)

    update = await adapter_answering(handler).check_update()
    assert update.available is False
    assert "non-JSON" in update.error


# --------------------------------------------------------------------------
# What the hub asks for
# --------------------------------------------------------------------------


async def test_the_node_answers_from_its_own_cache() -> None:
    """`recheck_now: false`, so polling every node does not make every node
    reach out to AdGuard's update server on the hub's timer."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"current_version": "v1"}, request=request)

    await adapter_answering(handler).check_update()
    assert seen == {"recheck_now": False}


# --------------------------------------------------------------------------
# A backend that cannot answer
# --------------------------------------------------------------------------


def test_the_default_says_it_has_nothing_to_report() -> None:
    """Adding this to the interface must not break an adapter that predates it."""
    from app.adapters.base import DnsAdapter

    assert "check_update" in dir(DnsAdapter)
    assert DnsAdapter.check_update is not None


async def test_a_fake_backend_reports_no_update(fake_adapter) -> None:
    update = await fake_adapter("http://a.local").check_update()
    assert isinstance(update, RemoteUpdate)
    assert update.available is False


# --------------------------------------------------------------------------
# Through the API
# --------------------------------------------------------------------------


async def test_the_instance_list_carries_the_update_fields(
    auth_client: httpx.AsyncClient, fake_adapter
) -> None:
    created = await auth_client.post(
        "/api/instances",
        json={"name": "a", "base_url": "http://a.local", "username": "admin", "password": "pw"},
    )
    assert created.status_code == 201, created.text

    body = (await auth_client.get("/api/instances")).json()
    assert body[0]["update_version"] == ""
    assert body[0]["update_url"] == ""
    assert "update_error" in body[0]


async def test_the_update_fields_did_not_open_a_credential_leak(
    auth_client: httpx.AsyncClient, fake_adapter
) -> None:
    """The instance payload grew; the rule about what it may never carry did not.

    Asserted on the secret itself and on the column that stores it, not on the
    word "password" — `has_password` contains that, which would have made this
    test fail on a payload that is perfectly correct.
    """
    secret = "correct-horse-battery-staple"
    await auth_client.post(
        "/api/instances",
        json={"name": "b", "base_url": "http://b.local", "username": "admin", "password": secret},
    )
    response = await auth_client.get("/api/instances")
    body = response.text

    assert secret not in body
    assert "password_encrypted" not in body
    # The positive half: the hub still says that one is stored.
    assert response.json()[0]["has_password"] is True


# --------------------------------------------------------------------------
# What is already in the database
# --------------------------------------------------------------------------


async def test_a_stored_update_to_the_running_version_is_not_shown(
    auth_client: httpx.AsyncClient,
) -> None:
    """Reported after the comparison was fixed: the card still said it.

    These fields are written by reconciliation and read back until the next run.
    A row written by an earlier build names the version the node is already
    running, and nothing in between re-examined it — so fixing the comparison
    changed what would be written next and left every card exactly as it was.
    """
    from app.db import session_scope
    from app.models import Instance

    from .test_sync import A, add_instance

    instance_id = await add_instance(auth_client, "a", A)
    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        row.version = "v0.107.79"
        row.update_version = "v0.107.79"
        row.update_url = "https://example.test/releases"
        await session.commit()

    body = (await auth_client.get("/api/instances")).json()[0]
    assert body["version"] == "v0.107.79"
    assert body["update_version"] == ""
    assert body["update_url"] == ""


async def test_a_genuinely_newer_stored_update_is_still_shown(
    auth_client: httpx.AsyncClient,
) -> None:
    from app.db import session_scope
    from app.models import Instance

    from .test_sync import A, add_instance

    instance_id = await add_instance(auth_client, "a", A)
    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        row.version = "v0.107.79"
        row.update_version = "v0.107.80"
        await session.commit()

    body = (await auth_client.get("/api/instances")).json()[0]
    assert body["update_version"] == "v0.107.80"


async def test_an_older_stored_update_is_not_offered_as_one(
    auth_client: httpx.AsyncClient,
) -> None:
    """"Different" would have offered a downgrade; the question is "newer"."""
    from app.db import session_scope
    from app.models import Instance

    from .test_sync import A, add_instance

    instance_id = await add_instance(auth_client, "a", A)
    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        row.version = "v0.107.79"
        row.update_version = "v0.107.60"
        await session.commit()

    assert (await auth_client.get("/api/instances")).json()[0]["update_version"] == ""


async def test_a_version_the_hub_cannot_parse_leaves_the_stored_update_alone(
    auth_client: httpx.AsyncClient,
) -> None:
    """An edge build is not evidence that the stored update is wrong."""
    from app.db import session_scope
    from app.models import Instance

    from .test_sync import A, add_instance

    instance_id = await add_instance(auth_client, "a", A)
    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        row.version = "unknown"
        row.update_version = "v0.107.80"
        await session.commit()

    assert (await auth_client.get("/api/instances")).json()[0]["update_version"] == "v0.107.80"


async def test_pressing_test_re_examines_the_update_line(
    auth_client: httpx.AsyncClient,
) -> None:
    """The obvious thing to try on a card that looks wrong, and it used to do nothing.

    check_instance refreshed the version, the status and last seen — every field
    on the card except the one the operator was looking at — so a wrong update
    line survived until the reconcile timer came round.
    """
    from app.db import session_scope
    from app.models import Instance

    from .test_sync import A, add_instance

    instance_id = await add_instance(auth_client, "a", A)
    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        row.update_version = "v0.107.79"
        await session.commit()

    assert (await auth_client.post(f"/api/instances/{instance_id}/test")).status_code == 200

    async with session_scope() as session:
        row = await session.get(Instance, instance_id)
        assert row is not None
        # Cleared in the database, not merely hidden on the way out.
        assert row.update_version == ""
