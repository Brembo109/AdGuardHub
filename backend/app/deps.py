"""Shared FastAPI dependencies."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import User
from .runtime import get_credentials, get_login_throttle, get_sessions
from .security import verify_password

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Its own logger, so an operator can raise or lower the volume on sign-ins
# without touching the rest of the hub.
auth_log = logging.getLogger("adguardhub.auth")

# Not a failure: the client has not been asked for credentials yet.
NO_CREDENTIALS = "no credentials presented"


async def admin_exists(session: AsyncSession) -> bool:
    result = await session.execute(select(User.id).limit(1))
    return result.first() is not None


async def current_user(request: Request, session: SessionDep) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    username = get_sessions().verify(token, settings.session_max_age)
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def client_source(request: Request) -> str:
    """What the throttle counts against — see services/throttle.py on why not XFF."""
    return request.client.host if request.client else "unknown"


def note_signin_failure(source: str, door: str, reason: str = "wrong password") -> None:
    """Count a failed sign-in, say so in the log, and keep it for the UI.

    Until recently a wrong password left no trace anywhere. It now leaves a log
    line — but every cause produced the same one, so "Failed sign-in" told an
    operator that something was wrong and nothing about what. ``reason`` is the
    difference between reading the log and having to guess.

    The attempted username is deliberately left out of all of it. The hub has one
    admin account, so the name adds nothing an operator does not already know,
    while recording it would capture a password the first time somebody types one
    into the username field.
    """
    throttle = get_login_throttle()
    count = throttle.record_failure(source, door=door, reason=reason)
    if count == throttle.max_failures:
        auth_log.warning(
            "Locked out %s after %d failed sign-ins (%s: %s); "
            "further attempts refused for %d seconds",
            source,
            count,
            door,
            reason,
            int(throttle.window),
        )
    else:
        auth_log.warning(
            "Failed sign-in from %s (%s: %s) — attempt %d of %d",
            source,
            door,
            reason,
            count,
            throttle.max_failures,
        )


def note_signin_success(source: str, door: str) -> None:
    """Clear the count and record that someone signed in.

    Only the two login forms report success. Basic Auth re-authenticates on every
    single request, so logging it here would bury everything else — the same
    problem this change exists to fix.
    """
    get_login_throttle().record_success(source)
    auth_log.info("Signed in from %s (%s)", source, door)


def enforce_login_throttle(request: Request) -> str:
    """Refuse a source that has failed too often, before any password is hashed.

    Hashing first would leave untouched the CPU cost an attacker can impose,
    which is half of what the throttle is for.
    """
    source = client_source(request)
    wait = get_login_throttle().retry_after(source)
    if wait > 0:
        # The lockout itself was logged once, when it started. Whoever tripped it
        # decides how many refusals follow, so these stay at debug rather than
        # handing an attacker a way to flood the log.
        auth_log.debug("Refused a sign-in from %s: locked out for another %.0f s", source, wait)
        seconds = int(wait) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts. Try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )
    return source


async def _user_from_basic_auth(
    request: Request, session: AsyncSession
) -> tuple[User | None, str]:
    """Resolve the admin from an ``Authorization: Basic`` header.

    AdGuard Home accepts Basic Auth on its whole /control surface, and that — not
    the login-and-cookie dance — is what most things built against it actually
    send: the phone remotes, the Home Assistant integration, one-line curl. A hub
    that only understood the cookie answered all of them with a bare 401, which a
    client can only report as "wrong credentials".

    Returns the user and an empty reason, or ``None`` and why it failed. The
    reason exists because every failure used to look identical from the outside
    *and* in the log — a wrong password, an unknown account and a header the
    server could not decode all produced one line reading "Failed sign-in", which
    is enough to know something is wrong and not enough to act on.

    ``NO_CREDENTIALS`` is its own answer and deliberately not a failure: a client
    that has not been asked for credentials yet has not got them wrong.
    """
    scheme, _, encoded = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None, NO_CREDENTIALS
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None, "the Authorization header is malformed"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Almost always a client that encoded a non-ASCII password as latin-1
        # while RFC 7617 asks for UTF-8. Worth its own message: it is the one
        # cause an operator has no way of guessing from a bare 401, and it looks
        # exactly like a wrong password from the outside.
        return None, "the credentials are not valid UTF-8 (a client encoding problem)"
    username, separator, password = decoded.partition(":")
    if not separator or not username:
        return None, "the Authorization header is malformed"

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        # The name is not in the message: it is attacker-supplied, and the first
        # time somebody types their password into the username box it would be
        # written to the log.
        return None, "no such account"

    cache = get_credentials()
    if cache.check(username, password):
        return user, ""
    # bcrypt is ~300 ms of straight CPU work; off the loop, or one request would
    # stall every other request and the background workers with it.
    if await asyncio.to_thread(verify_password, password, user.password_hash):
        cache.remember(username, password)
        return user, ""
    return None, "wrong password"


async def control_user(request: Request, session: SessionDep) -> User:
    """The admin, from either the session cookie or HTTP Basic Auth.

    Only the AdGuard-compatible surface accepts Basic: the hub's own API stays
    cookie-only, so presenting a password on every request is confined to the
    endpoints that exist precisely to be spoken to by other people's clients.
    """
    if request.cookies.get(get_settings().session_cookie):
        return await current_user(request, session)

    # Basic presents the password on every request, so this is the entry point an
    # attacker would hammer: checked before the hash, like the login forms.
    source = enforce_login_throttle(request)
    user, reason = await _user_from_basic_auth(request, session)
    if user is None:
        # A client with no credentials at all is not a failed sign-in, it is the
        # first half of the Basic Auth handshake: probe, receive 401 with
        # WWW-Authenticate, retry with credentials. Counting it meant every
        # attempt cost two, so ten allowed failures were really five — and any
        # unauthenticated request from a scanner or a monitoring check could use
        # up an address's whole allowance and lock out the person behind it.
        if reason != NO_CREDENTIALS:
            note_signin_failure(source, "Basic Auth", reason)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid username or password",
            # Without this a Basic client has nothing telling it to try again
            # with credentials, and reports the 401 as a flat rejection.
            headers={"WWW-Authenticate": 'Basic realm="AdGuardHub"'},
        )
    get_login_throttle().record_success(source)
    return user


ControlUser = Annotated[User, Depends(control_user)]
