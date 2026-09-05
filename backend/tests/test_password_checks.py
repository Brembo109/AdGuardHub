"""Where bcrypt runs, and what it costs for a name that does not exist.

bcrypt takes ~300 ms on purpose. Run on the event loop, that is 300 ms in which
nothing else in the hub moves — no push, no query log poll, no event stream —
and the login form is the one route anyone on the network can reach without a
session. And a sign-in for an unknown name used to skip the hash entirely, so
its answer came back a millisecond after the request: anyone could learn the
admin's username by timing two requests.
"""

from __future__ import annotations

import threading

import httpx
import pytest

from app import security


@pytest.fixture
def hashing(monkeypatch) -> list[threading.Thread]:
    """Every bcrypt call, and the thread it ran on."""
    seen: list[threading.Thread] = []
    real_verify, real_hash = security.verify_password, security.hash_password

    def verify(password: str, password_hash: str) -> bool:
        seen.append(threading.current_thread())
        return real_verify(password, password_hash)

    def hash_(password: str) -> str:
        seen.append(threading.current_thread())
        return real_hash(password)

    monkeypatch.setattr(security, "verify_password", verify)
    monkeypatch.setattr(security, "hash_password", hash_)
    return seen


def off_the_loop(seen: list[threading.Thread]) -> bool:
    return bool(seen) and all(thread is not threading.main_thread() for thread in seen)


async def test_an_unknown_name_costs_a_hash_like_a_known_one(
    auth_client: httpx.AsyncClient, hashing: list[threading.Thread]
) -> None:
    await auth_client.post("/api/auth/logout")

    hashing.clear()
    nobody = await auth_client.post(
        "/api/auth/login", json={"username": "nobody", "password": "supersecret"}
    )
    assert nobody.status_code == 401
    # The decoy hash is made on first use, then it is one check per attempt.
    assert len(hashing) >= 1
    hashing.clear()
    assert (
        await auth_client.post(
            "/api/auth/login", json={"username": "nobody", "password": "supersecret"}
        )
    ).status_code == 401
    unknown_cost = len(hashing)

    hashing.clear()
    wrong = await auth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "not-it"}
    )
    assert wrong.status_code == 401
    assert len(hashing) == unknown_cost == 1


async def test_the_adguard_login_costs_the_same_for_an_unknown_name(
    auth_client: httpx.AsyncClient, hashing: list[threading.Thread]
) -> None:
    await auth_client.post("/api/auth/logout")
    await auth_client.post("/control/login", json={"name": "nobody", "password": "x"})
    hashing.clear()

    assert (
        await auth_client.post("/control/login", json={"name": "nobody", "password": "x"})
    ).status_code == 403
    assert len(hashing) == 1


async def test_basic_auth_costs_the_same_for_an_unknown_name(
    auth_client: httpx.AsyncClient, hashing: list[threading.Thread]
) -> None:
    await auth_client.post("/api/auth/logout")
    await auth_client.get("/control/status", auth=("nobody", "x"))
    hashing.clear()

    assert (await auth_client.get("/control/status", auth=("nobody", "x"))).status_code == 401
    assert len(hashing) == 1
    # A wrong password for the real account is still the wrong password.
    assert (await auth_client.get("/control/status", auth=("admin", "x"))).status_code == 401
    assert (
        await auth_client.get("/control/status", auth=("admin", "supersecret"))
    ).status_code == 200


async def test_no_door_runs_bcrypt_on_the_event_loop(
    client: httpx.AsyncClient, hashing: list[threading.Thread]
) -> None:
    # First-run setup hashes the new password.
    setup = await client.post(
        "/api/auth/setup", json={"username": "admin", "password": "supersecret"}
    )
    assert setup.status_code == 200
    assert off_the_loop(hashing)

    # The hub's own login form.
    hashing.clear()
    await client.post("/api/auth/logout")
    login = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "supersecret"}
    )
    assert login.status_code == 200
    assert off_the_loop(hashing)

    # Changing the password checks the old one and hashes the new one.
    hashing.clear()
    changed = await client.post(
        "/api/auth/password",
        json={"current_password": "supersecret", "new_password": "anotherlongpassword"},
    )
    assert changed.status_code == 200
    assert len(hashing) == 2 and off_the_loop(hashing)

    # The AdGuard-compatible login, and Basic Auth on that surface.
    hashing.clear()
    await client.post("/api/auth/logout")
    assert (
        await client.post(
            "/control/login", json={"name": "admin", "password": "anotherlongpassword"}
        )
    ).status_code == 200
    assert off_the_loop(hashing)

    hashing.clear()
    await client.post("/api/auth/logout")
    assert (
        await client.get("/control/status", auth=("admin", "anotherlongpassword"))
    ).status_code == 200
    assert off_the_loop(hashing)
