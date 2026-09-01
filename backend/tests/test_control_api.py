"""The AdGuard-compatible surface, as a client app would use it.

The point is not shape-for-shape fidelity but behaviour: a client pointed at the hub
edits the hub, and the change reaches every instance.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


@pytest.fixture
async def app_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """A client authenticated the way an AdGuard app authenticates."""
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.post(
        "/control/login", json={"name": "admin", "password": "supersecret"}
    )
    assert response.status_code == 200, response.text
    return client


async def test_login_rejects_the_wrong_password(client: httpx.AsyncClient) -> None:
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.post("/control/login", json={"name": "admin", "password": "nope"})
    assert response.status_code == 403


async def test_endpoints_require_authentication(client: httpx.AsyncClient) -> None:
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")
    assert (await client.get("/control/status")).status_code == 401


async def test_status_describes_the_hub_not_a_single_node(
    app_client: httpx.AsyncClient,
) -> None:
    await add_instance(app_client, "a", A)
    await add_instance(app_client, "b", B)

    body = (await app_client.get("/control/status")).json()
    assert body["version"].startswith("AdGuardHub")
    assert sorted(body["dns_addresses"]) == sorted([A, B])
    # The hub never syncs DHCP, so it must not advertise it.
    assert body["dhcp_available"] is False


async def test_filtering_status_returns_the_hubs_own_state(
    app_client: httpx.AsyncClient,
) -> None:
    await app_client.post("/api/rules", json={"text": "||ads.example^"})
    await app_client.post(
        "/api/filter-lists", json={"name": "List", "url": "https://example.com/l.txt"}
    )

    body = (await app_client.get("/control/filtering/status")).json()
    assert body["user_rules"] == ["||ads.example^"]
    assert [item["url"] for item in body["filters"]] == ["https://example.com/l.txt"]


async def test_setting_rules_from_an_app_reaches_every_instance(
    app_client: httpx.AsyncClient,
) -> None:
    """The whole reason for this surface: one edit, every node."""
    await add_instance(app_client, "a", A)
    await add_instance(app_client, "b", B)

    response = await app_client.post(
        "/control/filtering/set_rules",
        json={"rules": ["||from-the-app.example^", "! a comment", "@@||allow.example^"]},
    )
    assert response.status_code == 200
    await drain_background()

    for url in (A, B):
        assert FakeAdapter.state_for(url).rules == [
            "||from-the-app.example^",
            "@@||allow.example^",
        ]


async def test_a_subscription_added_from_an_app_is_pushed(
    app_client: httpx.AsyncClient,
) -> None:
    await add_instance(app_client, "a", A)
    await app_client.post(
        "/control/filtering/add_url",
        json={"name": "From app", "url": "https://example.com/app.txt", "whitelist": False},
    )
    await drain_background()

    lists = FakeAdapter.state_for(A).filter_lists
    assert [item.url for item in lists] == ["https://example.com/app.txt"]

    await app_client.post(
        "/control/filtering/remove_url",
        json={"url": "https://example.com/app.txt", "whitelist": False},
    )
    await drain_background()
    assert FakeAdapter.state_for(A).filter_lists == []


async def test_dns_settings_written_from_an_app_are_merged_and_pushed(
    app_client: httpx.AsyncClient,
) -> None:
    await add_instance(app_client, "a", A)
    await app_client.patch(
        "/api/config/sections/dns",
        json={"managed": True, "data": {"upstream_dns": ["1.1.1.1"], "dnssec_enabled": True}},
    )
    await drain_background()

    # A partial write from the app must not drop the keys it did not mention.
    await app_client.post("/control/dns_config", json={"upstream_dns": ["9.9.9.9"]})
    await drain_background()

    assert FakeAdapter.state_for(A).sections["dns"] == {
        "upstream_dns": ["9.9.9.9"],
        "dnssec_enabled": True,
    }


async def test_protection_toggle_pauses_filtering_everywhere(
    app_client: httpx.AsyncClient,
) -> None:
    await add_instance(app_client, "a", A)
    await app_client.patch(
        "/api/config/sections/dns",
        json={"managed": True, "data": {"protection_enabled": True}},
    )
    await drain_background()

    await app_client.post("/control/protection", json={"enabled": False})
    await drain_background()
    assert FakeAdapter.state_for(A).sections["dns"]["protection_enabled"] is False

    assert (await app_client.get("/control/status")).json()["protection_enabled"] is False


async def test_safebrowsing_toggle_round_trips(app_client: httpx.AsyncClient) -> None:
    await app_client.post("/control/safebrowsing/enable")
    assert (await app_client.get("/control/safebrowsing/status")).json()["enabled"] is True

    await app_client.post("/control/safebrowsing/disable")
    assert (await app_client.get("/control/safebrowsing/status")).json()["enabled"] is False


async def test_querylog_is_returned_in_adguards_shape(app_client: httpx.AsyncClient) -> None:
    from .test_querylog import entry

    await add_instance(app_client, "a", A)
    FakeAdapter.state_for(A).query_log = [entry("ads.example.com", "2026-01-01T10:00:00Z")]
    await app_client.post("/api/querylog/refresh")

    body = (await app_client.get("/control/querylog")).json()
    row = body["data"][0]
    assert row["question"]["name"] == "ads.example.com"
    assert row["rules"] == [{"text": "||ads.example.com^"}]
    # Which node answered, for clients that surface it.
    assert row["client_info"]["name"] == "a"


async def test_stats_are_summed_across_instances(app_client: httpx.AsyncClient) -> None:
    await add_instance(app_client, "a", A)
    await add_instance(app_client, "b", B)
    FakeAdapter.state_for(A).stats = {
        "num_dns_queries": 100,
        "num_blocked_filtering": 10,
        "avg_processing_time": 2.0,
        "dns_queries": [1, 2, 3],
        "top_clients": [{"192.168.1.5": 7}],
    }
    FakeAdapter.state_for(B).stats = {
        "num_dns_queries": 300,
        "num_blocked_filtering": 5,
        "avg_processing_time": 6.0,
        "dns_queries": [4, 5, 6],
        "top_clients": [{"192.168.1.5": 3}, {"192.168.1.9": 1}],
    }

    body = (await app_client.get("/control/stats")).json()
    assert body["num_dns_queries"] == 400
    assert body["num_blocked_filtering"] == 15
    assert body["dns_queries"] == [5, 7, 9]
    # Weighted by query count, not a plain mean of 2 and 6.
    assert body["avg_processing_time"] == pytest.approx(5.0)
    assert body["top_clients"][0] == {"192.168.1.5": 10}
    assert body["adguardhub_instances_reporting"] == 2


async def test_stats_survive_an_unreachable_instance(app_client: httpx.AsyncClient) -> None:
    await add_instance(app_client, "a", A)
    await add_instance(app_client, "b", B)
    FakeAdapter.state_for(A).stats = {"num_dns_queries": 42}
    FakeAdapter.state_for(B).offline = True

    body = (await app_client.get("/control/stats")).json()
    assert body["num_dns_queries"] == 42
    assert body["adguardhub_instances_reporting"] == 1
    assert body["adguardhub_instances_total"] == 2


async def test_writes_from_an_app_appear_in_the_history(
    app_client: httpx.AsyncClient,
) -> None:
    await app_client.post("/control/filtering/set_rules", json={"rules": ["||x.example^"]})
    latest = (await app_client.get("/api/versions")).json()[0]
    assert "AdGuard API" in latest["label"]
    assert latest["author"] == "admin"


async def test_the_surface_can_be_switched_off(app_client: httpx.AsyncClient) -> None:
    await app_client.put("/api/settings/hub", json={"external_api_enabled": False})
    response = await app_client.get("/control/status")
    assert response.status_code == 404
    assert "switched off" in response.json()["detail"]


# --------------------------------------------------------------------------
# HTTP Basic Auth
#
# AdGuard Home accepts Basic on its whole /control surface, and that is what the
# phone remotes and the Home Assistant integration send. The hub understood only
# its own session cookie, so those clients got a bare 401 and could only report
# it as bad credentials — the web UI password was correct all along.
# --------------------------------------------------------------------------


async def test_basic_auth_is_accepted_on_the_control_surface(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.get("/control/status", auth=("admin", "supersecret"))
    assert response.status_code == 200, response.text
    assert response.json()["version"].startswith("AdGuardHub")


async def test_basic_auth_rejects_a_wrong_password_and_asks_again(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.get("/control/status", auth=("admin", "nope"))
    assert response.status_code == 401
    # Without the challenge a client has nothing telling it credentials are wanted.
    assert response.headers["WWW-Authenticate"] == 'Basic realm="AdGuardHub"'


@pytest.mark.parametrize(
    "header",
    ["Basic", "Basic !!!not-base64!!!", "Basic " + "YWRtaW4=", "Bearer sometoken", "nonsense"],
)
async def test_a_malformed_authorization_header_is_a_401_not_a_crash(
    client: httpx.AsyncClient, header: str
) -> None:
    """'YWRtaW4=' decodes to "admin" with no colon, so there is no password to check."""
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.get("/control/status", headers={"Authorization": header})
    assert response.status_code == 401


async def test_the_hubs_own_api_stays_cookie_only(client: httpx.AsyncClient) -> None:
    """Basic is for other people's clients; it does not widen the hub's own API."""
    await client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    await client.post("/api/auth/logout")

    response = await client.get("/api/instances", auth=("admin", "supersecret"))
    assert response.status_code == 401


async def test_a_changed_password_stops_working_at_once(
    auth_client: httpx.AsyncClient,
) -> None:
    """The credential cache must not keep the old password alive for its TTL.

    The cookie is dropped first, or it would answer these requests by itself: a
    session stays valid across a password change on purpose, so that changing it
    does not log you out of the tab you changed it in.
    """
    response = await auth_client.post(
        "/api/auth/password",
        json={"current_password": "supersecret", "new_password": "a-longer-secret"},
    )
    assert response.status_code == 200, response.text
    auth_client.cookies.clear()

    stale = await auth_client.get("/control/status", auth=("admin", "supersecret"))
    assert stale.status_code == 401
    fresh = await auth_client.get("/control/status", auth=("admin", "a-longer-secret"))
    assert fresh.status_code == 200


async def test_a_cookie_and_a_basic_header_together_prefer_the_cookie(
    auth_client: httpx.AsyncClient,
) -> None:
    """A live session is not overruled by whatever a client also puts in a header."""
    response = await auth_client.get("/control/status", auth=("admin", "quite-wrong"))
    assert response.status_code == 200
