"""The limit on how fast a password can be guessed.

Every way in ends at bcrypt, which was the only thing slowing an attacker down.
Two harms follow: guessing at whatever rate the CPU allows, and — since each
wrong password costs ~300 ms — spending the hub's cycles on purpose.

The failure modes worth pinning down are the ones where a throttle is worse than
none: locking the single admin out of their own hub, counting a header the
client controls, or refusing so late that the hash has already run.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.runtime import get_login_throttle
from app.services.throttle import MAX_TRACKED_SOURCES, LoginThrottle

BAD = {"username": "admin", "password": "wrong"}
GOOD = {"username": "admin", "password": "supersecret"}


@pytest.fixture(autouse=True)
def _clear_throttle():
    """The throttle is process-wide, so one test must not arm the next."""
    get_login_throttle()._sources.clear()  # noqa: SLF001
    yield
    get_login_throttle()._sources.clear()  # noqa: SLF001


@pytest_asyncio.fixture
async def from_elsewhere(fresh_db, fake_adapter):
    """A client whose requests arrive from a different address."""
    transport = httpx.ASGITransport(app=app, client=("10.9.9.9", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other:
        yield other


# --------------------------------------------------------------------------
# The counter itself
# --------------------------------------------------------------------------


def test_it_allows_up_to_the_limit_then_refuses() -> None:
    throttle = LoginThrottle(max_failures=3, window=60.0)
    for _ in range(2):
        throttle.record_failure("a", now=1_000.0)
        assert throttle.retry_after("a", now=1_000.0) == 0.0
    throttle.record_failure("a", now=1_000.0)
    assert throttle.retry_after("a", now=1_000.0) == pytest.approx(60.0)


def test_the_window_expires() -> None:
    throttle = LoginThrottle(max_failures=1, window=60.0)
    throttle.record_failure("a", now=1_000.0)
    assert throttle.retry_after("a", now=1_059.0) == pytest.approx(1.0)
    assert throttle.retry_after("a", now=1_060.0) == 0.0


def test_each_failure_restarts_the_clock() -> None:
    """Otherwise a slow trickle of guesses sits under the limit indefinitely."""
    throttle = LoginThrottle(max_failures=2, window=60.0)
    throttle.record_failure("a", now=1_000.0)
    throttle.record_failure("a", now=1_050.0)
    assert throttle.retry_after("a", now=1_051.0) == pytest.approx(59.0)


def test_a_correct_password_clears_the_slate() -> None:
    throttle = LoginThrottle(max_failures=1, window=60.0)
    throttle.record_failure("a", now=1_000.0)
    assert throttle.retry_after("a", now=1_000.0) > 0
    throttle.record_success("a")
    assert throttle.retry_after("a", now=1_000.0) == 0.0


def test_sources_are_counted_separately() -> None:
    throttle = LoginThrottle(max_failures=1, window=60.0)
    throttle.record_failure("a", now=1_000.0)
    assert throttle.retry_after("a", now=1_000.0) > 0
    assert throttle.retry_after("b", now=1_000.0) == 0.0


def test_the_table_cannot_grow_without_limit() -> None:
    """An attacker varying their source address must not become a memory leak."""
    throttle = LoginThrottle(max_failures=1, window=60.0)
    for index in range(MAX_TRACKED_SOURCES + 200):
        throttle.record_failure(f"source-{index}", now=1_000.0)
    assert len(throttle._sources) <= MAX_TRACKED_SOURCES  # noqa: SLF001


# --------------------------------------------------------------------------
# The three ways in
# --------------------------------------------------------------------------


async def test_the_hubs_login_form_locks_out_after_enough_failures(
    auth_client: httpx.AsyncClient,
) -> None:
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures):
        assert (await auth_client.post("/api/auth/login", json=BAD)).status_code == 401

    refused = await auth_client.post("/api/auth/login", json=BAD)
    assert refused.status_code == 429
    assert "Retry-After" in refused.headers
    assert int(refused.headers["Retry-After"]) > 0

    # And the right password is refused too, or the lockout would be trivial to
    # step around by guessing the real one last.
    assert (await auth_client.post("/api/auth/login", json=GOOD)).status_code == 429


async def test_the_adguard_login_shares_the_same_limit(
    auth_client: httpx.AsyncClient,
) -> None:
    """One counter per source, not one per door — otherwise the limit is doubled."""
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures):
        await auth_client.post("/control/login", json={"name": "admin", "password": "wrong"})

    refused = await auth_client.post("/api/auth/login", json=BAD)
    assert refused.status_code == 429


async def test_basic_auth_is_throttled_too(auth_client: httpx.AsyncClient) -> None:
    """The endpoint that carries a password on every request is the one to hammer."""
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures):
        assert (
            await auth_client.get("/control/status", auth=("admin", "wrong"))
        ).status_code == 401

    assert (await auth_client.get("/control/status", auth=("admin", "wrong"))).status_code == 429


async def test_a_few_typos_cost_nothing(auth_client: httpx.AsyncClient) -> None:
    """A throttle that punishes ordinary mistakes would just be an outage."""
    await auth_client.post("/api/auth/logout")

    for _ in range(3):
        assert (await auth_client.post("/api/auth/login", json=BAD)).status_code == 401
    assert (await auth_client.post("/api/auth/login", json=GOOD)).status_code == 200

    # The successful sign-in cleared the count, so the next slip starts over.
    await auth_client.post("/api/auth/logout")
    assert (await auth_client.post("/api/auth/login", json=BAD)).status_code == 401


async def test_the_admin_is_never_locked_out_of_their_own_hub(
    auth_client: httpx.AsyncClient, from_elsewhere: httpx.AsyncClient
) -> None:
    """The single most important property here.

    With one admin account, counting failures against the *account* would let any
    device on the network lock the operator out for as long as it cared to keep
    guessing — a denial of service wearing a security feature's clothes.
    """
    await auth_client.post("/api/auth/setup", json={"username": "admin", "password": "supersecret"})
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures + 5):
        await from_elsewhere.post("/api/auth/login", json=BAD)
    assert (await from_elsewhere.post("/api/auth/login", json=GOOD)).status_code == 429

    # The operator, at their own machine, is untouched.
    assert (await auth_client.post("/api/auth/login", json=GOOD)).status_code == 200


async def test_a_forwarded_for_header_cannot_buy_a_fresh_allowance(
    auth_client: httpx.AsyncClient,
) -> None:
    """Trusting that header would let one attacker be an unlimited number of them."""
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures):
        await auth_client.post("/api/auth/login", json=BAD)

    refused = await auth_client.post(
        "/api/auth/login", json=BAD, headers={"X-Forwarded-For": "203.0.113.7"}
    )
    assert refused.status_code == 429


async def test_a_refused_attempt_never_reaches_bcrypt(
    auth_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half the point is the CPU cost, so refusing after the hash would be no fix.

    Asserted structurally rather than by timing, which would be flaky on a shared
    runner: the password check simply must not be called.
    """
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()
    for _ in range(throttle.max_failures):
        await auth_client.post("/api/auth/login", json=BAD)

    calls: list[str] = []
    import app.api.auth as auth_module

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password)
        return False

    monkeypatch.setattr(auth_module, "verify_password", spy)

    assert (await auth_client.post("/api/auth/login", json=BAD)).status_code == 429
    assert calls == [], "the password was hashed despite the source being locked out"
