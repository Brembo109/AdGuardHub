"""Shared FastAPI dependencies."""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_session
from .models import User
from .runtime import get_credentials, get_sessions
from .security import verify_password

SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
    user = await _user_from_basic_auth(request, session)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid username or password",
            # Without this a Basic client has nothing telling it to try again
            # with credentials, and reports the 401 as a flat rejection.
            headers={"WWW-Authenticate": 'Basic realm="AdGuardHub"'},
        )
    return user


ControlUser = Annotated[User, Depends(control_user)]
