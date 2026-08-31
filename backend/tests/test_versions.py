"""Version history: what a change carried, how two points differ, and rollback."""

from __future__ import annotations

import httpx

from app.services.sync import drain_background

from .fakes import FakeAdapter
from .test_sync import A, B, add_instance


async def test_every_change_records_a_version(auth_client: httpx.AsyncClient) -> None:
    await auth_client.post("/api/rules", json={"text": "||one.example^"})
    await auth_client.post("/api/rules", json={"text": "||two.example^"})

    versions = (await auth_client.get("/api/versions")).json()
    assert [item["label"] for item in versions] == [
        "rule added: ||two.example^",
        "rule added: ||one.example^",
    ]
    assert versions[0]["author"] == "admin"
    # Newest first, and each says what changed relative to its predecessor.
    assert "1 added" in versions[0]["summary"]


async def test_a_change_that_changes_nothing_makes_no_version(
    auth_client: httpx.AsyncClient,
) -> None:
    """Pushes are full-state and fire on every edit; versions must not follow blindly."""
    await auth_client.post("/api/rules", json={"text": "||one.example^"})
    before = len((await auth_client.get("/api/versions")).json())

    # A duplicate is rejected, so the state is untouched.
    duplicate = await auth_client.post("/api/rules", json={"text": "||one.example^"})
    assert duplicate.status_code == 409
    assert len((await auth_client.get("/api/versions")).json()) == before


async def test_diff_against_the_current_state(auth_client: httpx.AsyncClient) -> None:
    first = await auth_client.post("/api/rules", json={"text": "||one.example^"})
    assert first.status_code == 201
    versions = (await auth_client.get("/api/versions")).json()
    version_id = versions[0]["id"]

    await auth_client.post("/api/rules", json={"text": "||two.example^"})
    await auth_client.post(
        "/api/filter-lists", json={"name": "L", "url": "https://example.com/l.txt"}
    )

    diff = (await auth_client.get(f"/api/versions/{version_id}/diff")).json()
    assert diff["to_label"] == "current state"
    assert diff["changes"]["rules"]["added"] == ["||two.example^"]
    assert diff["changes"]["filter_lists"]["added"] == ["blocklist:https://example.com/l.txt"]
    assert diff["changes"]["empty"] is False


async def test_diff_between_two_versions_includes_sections(
    auth_client: httpx.AsyncClient,
) -> None:
    await auth_client.patch(
        "/api/config/sections/dns", json={"managed": True, "data": {"upstream_dns": ["1.1.1.1"]}}
    )
    early = (await auth_client.get("/api/versions")).json()[0]["id"]

    await auth_client.patch(
        "/api/config/sections/dns", json={"managed": True, "data": {"upstream_dns": ["9.9.9.9"]}}
    )
    late = (await auth_client.get("/api/versions")).json()[0]["id"]

    diff = (await auth_client.get(f"/api/versions/{early}/diff?against={late}")).json()
    change = diff["changes"]["sections"]["dns"]["keys"]["upstream_dns"]
    assert change["before"] == ["1.1.1.1"]
    assert change["after"] == ["9.9.9.9"]


async def test_rollback_restores_state_and_pushes_it(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)

    await auth_client.post("/api/rules", json={"text": "||keep.example^"})
    await drain_background()
    good = (await auth_client.get("/api/versions")).json()[0]["id"]

    # A change the operator regrets.
    await auth_client.post("/api/rules", json={"text": "||oops.example^"})
    await drain_background()
    assert sorted(FakeAdapter.state_for(A).rules) == ["||keep.example^", "||oops.example^"]

    result = (await auth_client.post(f"/api/versions/{good}/restore")).json()
    assert result["rules"] == 1
    await drain_background()

    assert [rule["text"] for rule in (await auth_client.get("/api/rules")).json()] == [
        "||keep.example^"
    ]
    # The instances follow, so a rollback actually undoes the mistake everywhere.
    assert FakeAdapter.state_for(A).rules == ["||keep.example^"]


async def test_rollback_is_itself_recorded(auth_client: httpx.AsyncClient) -> None:
    await auth_client.post("/api/rules", json={"text": "||keep.example^"})
    good = (await auth_client.get("/api/versions")).json()[0]["id"]
    await auth_client.post("/api/rules", json={"text": "||oops.example^"})

    await auth_client.post(f"/api/versions/{good}/restore")
    latest = (await auth_client.get("/api/versions")).json()[0]
    assert latest["kind"] == "restore"
    assert f"rolled back to version {good}" in latest["label"]


async def test_rollback_restores_sections_too(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    await auth_client.patch(
        "/api/config/sections/dns", json={"managed": True, "data": {"upstream_dns": ["1.1.1.1"]}}
    )
    good = (await auth_client.get("/api/versions")).json()[0]["id"]

    await auth_client.patch(
        "/api/config/sections/dns", json={"managed": True, "data": {"upstream_dns": ["8.8.8.8"]}}
    )
    await drain_background()
    assert FakeAdapter.state_for(A).sections["dns"] == {"upstream_dns": ["8.8.8.8"]}

    await auth_client.post(f"/api/versions/{good}/restore")
    await drain_background()
    assert FakeAdapter.state_for(A).sections["dns"] == {"upstream_dns": ["1.1.1.1"]}


async def test_import_adopts_every_section_the_master_exposes(
    auth_client: httpx.AsyncClient,
) -> None:
    master = await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)

    FakeAdapter.state_for(A).sections = {
        "dns": {"upstream_dns": ["9.9.9.9"]},
        "clients": {"clients": [{"name": "nas", "ids": ["10.0.0.5"]}]},
        "safesearch": {"enabled": True},
    }
    FakeAdapter.state_for(A).unsupported_sections = {"tls"}

    result = (await auth_client.post(f"/api/instances/{master}/import", json={})).json()
    assert set(result["sections_imported"]) == {"dns", "clients", "safesearch"}
    assert "tls" in result["sections_unsupported"]
    await drain_background()

    # The whole configuration lands on the second node, not just the rules.
    assert FakeAdapter.state_for(B).sections["dns"] == {"upstream_dns": ["9.9.9.9"]}
    assert FakeAdapter.state_for(B).sections["clients"] == {
        "clients": [{"name": "nas", "ids": ["10.0.0.5"]}]
    }


async def test_dashboard_reports_the_last_sync(auth_client: httpx.AsyncClient) -> None:
    await add_instance(auth_client, "a", A)
    assert (await auth_client.get("/api/dashboard")).json()["last_sync_at"] is None

    await auth_client.post("/api/rules", json={"text": "||ads.example^"})
    await drain_background()

    stats = (await auth_client.get("/api/dashboard")).json()
    assert stats["last_sync_at"] is not None
    assert stats["instances_synced"] == 1
    assert stats["versions_total"] >= 1


async def test_a_risky_section_is_adopted_but_not_switched_on(
    auth_client: httpx.AsyncClient,
) -> None:
    """Encryption must not start replicating just because a master had it on.

    Enabling it on a node without a certificate makes that node unreachable, and an
    import is not an informed decision about that.
    """
    master = await add_instance(auth_client, "a", A)
    await add_instance(auth_client, "b", B)
    FakeAdapter.state_for(A).sections = {
        "tls": {"enabled": True},
        "dns": {"upstream_dns": ["1.1.1.1"]},
    }

    result = (await auth_client.post(f"/api/instances/{master}/import", json={})).json()
    assert result["sections_needing_review"] == ["tls"]
    await drain_background()

    listed = {item["name"]: item for item in (await auth_client.get("/api/config/sections")).json()}
    # Adopted, so the value is there to review…
    assert listed["tls"]["data"] == {"enabled": True}
    # …but not replicated, and never pushed.
    assert listed["tls"]["managed"] is False
    assert "tls" not in FakeAdapter.state_for(B).sections

    # A section without that hazard is switched on as before.
    assert listed["dns"]["managed"] is True
    assert FakeAdapter.state_for(B).sections["dns"] == {"upstream_dns": ["1.1.1.1"]}


async def test_the_risky_section_carries_its_warning(auth_client: httpx.AsyncClient) -> None:
    listed = {item["name"]: item for item in (await auth_client.get("/api/config/sections")).json()}
    tls = listed["tls"]
    assert tls["risky"] is True
    assert "certificate" in tls["notes"]
    assert "unreachable" in tls["notes"]
    # Only TLS is flagged; the warning must stay meaningful.
    assert [name for name, item in listed.items() if item["risky"]] == ["tls"]
