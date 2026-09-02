"""Failed sign-ins: counted correctly, explained, and visible without a shell.

Three things came out of one operator trying to connect a phone app and getting
"invalid authentication" with no way to find out why.

**An unauthenticated request was counted as a failed sign-in.** Basic Auth is a
handshake: the client asks, gets 401 with WWW-Authenticate, then asks again with
credentials. Counting the first half meant every real attempt cost two, so ten
allowed failures were really five — and any unauthenticated request from a
scanner or a monitoring check could spend an address's whole allowance.

**Every failure produced the same log line.** A wrong password, an unknown
account and a header that would not decode were indistinguishable, which is
enough to know something is wrong and not enough to act on.

**The lockout was invisible from inside the hub.** For five minutes the correct
password is refused, and nothing in the interface says so.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.runtime import get_login_throttle

GOOD = ("admin", "supersecret")


def _basic(user: str, password: str, encoding: str = "utf-8") -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode(encoding)).decode()
    return {"Authorization": f"Basic {raw}"}


@pytest.fixture(autouse=True)
def _clear_throttle():
    throttle = get_login_throttle()
    throttle._sources.clear()  # noqa: SLF001
    throttle._recent.clear()  # noqa: SLF001
    yield
    throttle._sources.clear()  # noqa: SLF001
    throttle._recent.clear()  # noqa: SLF001


# --------------------------------------------------------------------------
# The handshake is not a failure
# --------------------------------------------------------------------------


async def test_a_request_without_credentials_is_not_counted(
    auth_client: httpx.AsyncClient,
) -> None:
    """The half of Basic Auth that exists to *ask* for credentials.

    Before this, probing cost an attempt, so an operator got five real tries out
    of ten — and their phone app, which probes before every attempt, burned the
    allowance twice as fast as the log suggested.
    """
    await auth_client.post("/api/auth/logout")
    for _ in range(20):
        response = await auth_client.get("/control/status")
        assert response.status_code == 401
        assert "Basic" in response.headers.get("WWW-Authenticate", "")

    # Asserted through behaviour rather than the throttle's internals: twice the
    # allowance in probes, and the right password still works.
    assert (
        await auth_client.get("/control/status", headers=_basic(*GOOD))
    ).status_code == 200


async def test_the_full_allowance_is_available_for_real_attempts(
    auth_client: httpx.AsyncClient,
) -> None:
    """Probe-then-attempt, the way a client actually behaves."""
    await auth_client.post("/api/auth/logout")
    throttle = get_login_throttle()

    for _ in range(throttle.max_failures - 1):
        await auth_client.get("/control/status")  # the probe
        assert (
            await auth_client.get("/control/status", headers=_basic("admin", "wrong"))
        ).status_code == 401

    # Nine real failures out of ten allowed, even though eighteen requests were
    # refused. Before this the same sequence was already a lockout.
    assert (
        await auth_client.get("/control/status", headers=_basic(*GOOD))
    ).status_code == 200


# --------------------------------------------------------------------------
# Saying why
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (_basic("admin", "wrong"), "wrong password"),
        (_basic("nobody", "supersecret"), "no such account"),
        ({"Authorization": "Basic !!!not-base64!!!"}, "malformed"),
        ({"Authorization": f"Basic {base64.b64encode(b'noseparator').decode()}"}, "malformed"),
    ],
)
async def test_the_reason_reaches_the_log_and_the_api(
    auth_client: httpx.AsyncClient, headers: dict[str, str], expected: str
) -> None:
    await auth_client.post("/api/auth/logout")
    assert (await auth_client.get("/control/status", headers=headers)).status_code == 401

    await auth_client.post("/api/auth/login", json={"username": GOOD[0], "password": GOOD[1]})
    body = (await auth_client.get("/api/settings/sign-ins")).json()
    assert body["failures"], "the failure was not recorded"
    assert expected in body["failures"][0]["reason"]


async def test_a_latin1_password_is_named_rather_than_silently_refused(
    auth_client: httpx.AsyncClient,
) -> None:
    """A client encoding a non-ASCII password as latin-1 rather than UTF-8.

    Indistinguishable from a wrong password until the reason was recorded, and
    the one cause an operator has no way of guessing.
    """
    await auth_client.post("/api/auth/logout")
    await auth_client.get("/control/status", headers=_basic("admin", "Käse", "latin-1"))

    await auth_client.post("/api/auth/login", json={"username": GOOD[0], "password": GOOD[1]})
    body = (await auth_client.get("/api/settings/sign-ins")).json()
    assert "UTF-8" in body["failures"][0]["reason"]


async def test_no_username_or_password_is_ever_recorded(
    auth_client: httpx.AsyncClient,
) -> None:
    """Someone types their password into the username box on the first try."""
    await auth_client.post("/api/auth/logout")
    await auth_client.get("/control/status", headers=_basic("hunter2-my-password", "x"))

    await auth_client.post("/api/auth/login", json={"username": GOOD[0], "password": GOOD[1]})
    body = (await auth_client.get("/api/settings/sign-ins")).json()
    recorded = str(body["failures"])
    assert "hunter2" not in recorded
    assert "supersecret" not in recorded


# --------------------------------------------------------------------------
# Seeing the lockout from inside
# --------------------------------------------------------------------------


async def test_the_page_knows_the_limit_it_is_reporting_against(
    auth_client: httpx.AsyncClient,
) -> None:
    """So the UI can say "3 of 10" without hard-coding the rule."""
    throttle = get_login_throttle()
    body = (await auth_client.get("/api/settings/sign-ins")).json()
    assert body["max_failures"] == throttle.max_failures
    assert body["window_seconds"] == int(throttle.window)
    assert body["lockouts"] == []


async def test_lockouts_list_the_address_and_seconds_left() -> None:
    """Read from the throttle rather than inferred from timestamps in the UI."""
    from app.services.throttle import LoginThrottle

    throttle = LoginThrottle(max_failures=2, window=300.0)
    for _ in range(2):
        throttle.record_failure("10.0.0.9", now=1_000.0, door="Basic Auth", reason="wrong password")
    throttle.record_failure("10.0.0.8", now=1_000.0, door="Basic Auth", reason="wrong password")

    locked = throttle.lockouts(now=1_010.0)
    assert [source for source, _ in locked] == ["10.0.0.9"], "only the source over the limit"
    assert locked[0][1] == pytest.approx(290.0)


async def test_the_remembered_list_is_bounded() -> None:
    """Diagnostic detail, not an audit log — it must not grow without limit."""
    from app.services.throttle import MAX_REMEMBERED_FAILURES, LoginThrottle

    throttle = LoginThrottle()
    for index in range(MAX_REMEMBERED_FAILURES + 25):
        throttle.record_failure(f"10.0.0.{index}", door="Basic Auth", reason="wrong password")
    assert len(throttle.recent_failures()) == MAX_REMEMBERED_FAILURES


async def test_the_newest_failure_comes_first() -> None:
    from app.services.throttle import LoginThrottle

    throttle = LoginThrottle()
    throttle.record_failure("10.0.0.1", door="Basic Auth", reason="first")
    throttle.record_failure("10.0.0.2", door="Basic Auth", reason="second")
    assert throttle.recent_failures()[0].reason == "second"
