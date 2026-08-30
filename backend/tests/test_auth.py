from __future__ import annotations

import httpx


async def test_setup_required_before_first_admin(client: httpx.AsyncClient) -> None:
    state = (await client.get("/api/auth/state")).json()
    assert state["setup_required"] is True
    assert state["authenticated"] is False


async def test_protected_routes_require_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/rules")).status_code == 401
    assert (await client.get("/api/instances")).status_code == 401


async def test_setup_then_login_logout(client: httpx.AsyncClient) -> None:
    setup = await client.post(
        "/api/auth/setup", json={"username": "admin", "password": "supersecret"}
    )
    assert setup.status_code == 200
    assert (await client.get("/api/rules")).status_code == 200

    # Setup is a one-shot: a second call must not silently replace the admin.
    again = await client.post(
        "/api/auth/setup", json={"username": "mallory", "password": "supersecret"}
    )
    assert again.status_code == 409

    await client.post("/api/auth/logout")
    assert (await client.get("/api/rules")).status_code == 401

    bad = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    good = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "supersecret"}
    )
    assert good.status_code == 200
    assert (await client.get("/api/rules")).status_code == 200


async def test_password_change(auth_client: httpx.AsyncClient) -> None:
    wrong = await auth_client.post(
        "/api/auth/password",
        json={"current_password": "nope", "new_password": "anotherlongpassword"},
    )
    assert wrong.status_code == 403

    ok = await auth_client.post(
        "/api/auth/password",
        json={"current_password": "supersecret", "new_password": "anotherlongpassword"},
    )
    assert ok.status_code == 200

    await auth_client.post("/api/auth/logout")
    login = await auth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "anotherlongpassword"}
    )
    assert login.status_code == 200
