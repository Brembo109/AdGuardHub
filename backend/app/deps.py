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


def note_signin_failure(source: str, door: str) -> None:
    """Count a wrong password and say so in the log.

    Until now a wrong password left no trace anywhere: no log line, nothing in
    the UI. Someone working through a password list looked exactly like silence,
    and so did an operator locked out by the throttle wondering why.

    The attempted username is deliberately left out. The hub has one admin
    account, so the name adds nothing an operator does not already know, while
    logging it would write a password to disk the first time someone types one
    into the username field.
    """
    throttle = get_login_throttle()
    count = throttle.record_failure(source)
    if count == throttle.max_failures:
        auth_log.warning(
            "Locked out %s after %d failed sign-ins (%s); further attempts refused for %d seconds",
            source,
            count,
            door,
            int(throttle.window),
        )
    else:
        auth_log.warning(
            "Failed sign-in from %s (%s) — attempt %d of %d", source, door, count,
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


async def _user_from_basic_auth(request: Request, session: AsyncSession) -> User | None:
    """Resolve the admin from an ``Authorization: Basic`` header, or None.

    AdGuard Home accepts Basic Auth on its whole /control surface, and that — not
    the login-and-cookie dance — is what most things built against it actually
    send: the phone remotes, the Home Assistant integration, one-line curl. A hub
    that only understood the cookie answered all of them with a bare 401, which a
    client can only report as "wrong credentials".
    """
    scheme, _, encoded = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if not separator or not username:
        return None

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        return None

    cache = get_credentials()
    if cache.check(username, password):
        return user
    # bcrypt is ~300 ms of straight CPU work; off the loop, or one request would
    # stall every other request and the background workers with it.
    if await asyncio.to_thread(verify_password, password, user.password_hash):
        cache.remember(username, password)
        return user
    return None


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
    user = await _user_from_basic_auth(request, session)
    if user is None:
        note_signin_failure(source, "Basic Auth")
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
