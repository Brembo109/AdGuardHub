"""Single-admin authentication (spec §11)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import (
    CurrentUser,
    SessionDep,
    admin_exists,
    enforce_login_throttle,
    note_signin_failure,
    note_signin_success,
    session_user,
)
from ..models import User
from ..runtime import get_credentials, get_sessions, using_ephemeral_secret
from ..schemas import AuthState, LoginRequest, PasswordChange, SetupRequest
from ..security import check_password, make_password_hash
from ..services import hubsettings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        get_sessions().issue(user.username, user.password_hash),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/state", response_model=AuthState)
async def auth_state(request: Request, session: SessionDep) -> AuthState:
    setup_required = not await admin_exists(session)
    user = await session_user(request, session)
    return AuthState(
        authenticated=user is not None and not setup_required,
        username=user.username if user is not None else None,
        setup_required=setup_required,
        ephemeral_secret=using_ephemeral_secret(),
        onboarding_done=await hubsettings.onboarding_done(session),
    )


@router.post("/setup", response_model=AuthState)
async def setup(payload: SetupRequest, response: Response, session: SessionDep) -> AuthState:
    """Create the admin account. Only available while no account exists."""
    if await admin_exists(session):
        raise HTTPException(status.HTTP_409_CONFLICT, "An admin account already exists")
    user = User(username=payload.username, password_hash=await make_password_hash(payload.password))
    session.add(user)
    await session.commit()
    _set_cookie(response, user)
    return AuthState(authenticated=True, username=user.username, setup_required=False)


@router.post("/login", response_model=AuthState)
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> AuthState:
    source = enforce_login_throttle(request)
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalars().first()
    if not await check_password(payload.password, user.password_hash if user else None):
        note_signin_failure(source, "hub login")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    note_signin_success(source, "hub login")
    _set_cookie(response, user)
    return AuthState(authenticated=True, username=user.username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(get_settings().session_cookie, path="/")
    return {"ok": True}


@router.post("/password")
async def change_password(
    payload: PasswordChange, user: CurrentUser, response: Response, session: SessionDep
) -> dict[str, bool]:
    if not await check_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    user.password_hash = await make_password_hash(payload.new_password)
    await session.commit()
    # The Basic Auth cache holds credentials that were accepted; the old password
    # must stop working here at the same moment it stops working everywhere else.
    get_credentials().forget_all()
    # Every session cookie is tied to the password it was issued under, so the
    # change just ended all of them — including the one this request came in
    # on. That one is re-issued: the person who changed the password is the one
    # person who should not be signed out by it.
    _set_cookie(response, user)
    return {"ok": True}
