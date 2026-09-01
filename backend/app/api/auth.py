"""Single-admin authentication (spec §11)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..deps import CurrentUser, SessionDep, admin_exists, enforce_login_throttle
from ..models import User
from ..runtime import (
    get_credentials,
    get_login_throttle,
    get_sessions,
    using_ephemeral_secret,
)
from ..schemas import AuthState, LoginRequest, PasswordChange, SetupRequest
from ..security import hash_password, verify_password
from ..services import hubsettings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, username: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        get_sessions().issue(username),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/state", response_model=AuthState)
async def auth_state(request: Request, session: SessionDep) -> AuthState:
    settings = get_settings()
    setup_required = not await admin_exists(session)
    token = request.cookies.get(settings.session_cookie)
    username = get_sessions().verify(token, settings.session_max_age) if token else None
    return AuthState(
        authenticated=username is not None and not setup_required,
        username=username,
        setup_required=setup_required,
        ephemeral_secret=using_ephemeral_secret(),
        onboarding_done=await hubsettings.onboarding_done(session),
    )


@router.post("/setup", response_model=AuthState)
async def setup(payload: SetupRequest, response: Response, session: SessionDep) -> AuthState:
    """Create the admin account. Only available while no account exists."""
    if await admin_exists(session):
        raise HTTPException(status.HTTP_409_CONFLICT, "An admin account already exists")
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    session.add(user)
    await session.commit()
    _set_cookie(response, user.username)
    return AuthState(authenticated=True, username=user.username, setup_required=False)


@router.post("/login", response_model=AuthState)
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> AuthState:
    source = enforce_login_throttle(request)
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        get_login_throttle().record_failure(source)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    get_login_throttle().record_success(source)
    _set_cookie(response, user.username)
    return AuthState(authenticated=True, username=user.username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(get_settings().session_cookie, path="/")
    return {"ok": True}


@router.post("/password")
async def change_password(
    payload: PasswordChange, user: CurrentUser, session: SessionDep
) -> dict[str, bool]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    # The Basic Auth cache holds credentials that were accepted; the old password
    # must stop working here at the same moment it stops working everywhere else.
    get_credentials().forget_all()
    return {"ok": True}
