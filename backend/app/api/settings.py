"""Operational settings and notification targets (spec §10)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import CurrentUser, SessionDep
from ..models import NotifierTarget
from ..runtime import get_login_throttle
from ..schemas import (
    HubSettingsOut,
    HubSettingsUpdate,
    NotifierCreate,
    NotifierOut,
    NotifierUpdate,
)
from ..services import hubsettings
from ..services.notify import KNOWN_EVENTS, NOTIFIER_TYPES, test_target

router = APIRouter(prefix="/api/settings", tags=["settings"])


def to_out(target: NotifierTarget) -> NotifierOut:
    return NotifierOut(
        id=target.id,
        name=target.name,
        type=target.type,
        url=target.url,
        has_token=bool(target.token),
        enabled=target.enabled,
        events=[item for item in (target.events or "").split(",") if item],
        last_error=target.last_error,
    )


def _validate_events(events: list[str]) -> str:
    unknown = [event for event in events if event not in KNOWN_EVENTS]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown event(s): {', '.join(unknown)}"
        )
    return ",".join(events)


@router.post("/onboarding-complete", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def onboarding_complete(_: CurrentUser, session: SessionDep) -> None:
    """The first-run walkthrough is done, or the operator chose to skip it."""
    await hubsettings.finish_onboarding(session)


@router.get("/sign-ins")
async def failed_sign_ins(_: CurrentUser) -> dict[str, Any]:
    """Failed sign-ins and any lockout in force.

    The throttle refuses an address for five minutes after enough failures, and
    until now that was invisible from inside the hub: the operator saw the same
    rejection as an attacker would, with nothing to say the password was fine and
    the address was simply not being listened to. Reading the log meant leaving
    the interface for a shell.
    """
    throttle = get_login_throttle()
    return {
        "failures": [
            {
                "source": item.source,
                "door": item.door,
                "reason": item.reason,
                "at": item.at.isoformat().replace("+00:00", "Z"),
            }
            for item in throttle.recent_failures()
        ],
        "lockouts": [
            {"source": source, "seconds_left": int(seconds) + 1}
            for source, seconds in throttle.lockouts()
        ],
        "max_failures": throttle.max_failures,
        "window_seconds": int(throttle.window),
    }


@router.get("/notifiers/meta")
async def notifier_meta(_: CurrentUser) -> dict[str, list[str]]:
    return {"types": list(NOTIFIER_TYPES), "events": list(KNOWN_EVENTS)}


@router.get("/notifiers", response_model=list[NotifierOut])
async def list_notifiers(_: CurrentUser, session: SessionDep) -> list[NotifierOut]:
    result = await session.execute(select(NotifierTarget).order_by(NotifierTarget.id.asc()))
    return [to_out(target) for target in result.scalars().all()]


@router.post("/notifiers", response_model=NotifierOut, status_code=status.HTTP_201_CREATED)
async def create_notifier(
    payload: NotifierCreate, _: CurrentUser, session: SessionDep
) -> NotifierOut:
    target = NotifierTarget(
        name=payload.name,
        type=payload.type,
        url=payload.url,
        token=payload.token,
        enabled=payload.enabled,
        events=_validate_events(payload.events),
    )
    session.add(target)
    await session.commit()
    return to_out(target)


@router.patch("/notifiers/{target_id}", response_model=NotifierOut)
async def update_notifier(
    target_id: int, payload: NotifierUpdate, _: CurrentUser, session: SessionDep
) -> NotifierOut:
    target = await session.get(NotifierTarget, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notifier not found")
    data = payload.model_dump(exclude_unset=True)
    if "events" in data:
        target.events = _validate_events(data.pop("events") or [])
    for field, value in data.items():
        setattr(target, field, value)
    await session.commit()
    return to_out(target)


@router.delete(
    "/notifiers/{target_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_notifier(target_id: int, _: CurrentUser, session: SessionDep) -> None:
    target = await session.get(NotifierTarget, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notifier not found")
    await session.delete(target)
    await session.commit()


@router.post("/notifiers/{target_id}/test")
async def test_notifier(target_id: int, _: CurrentUser, session: SessionDep) -> dict[str, str]:
    target = await session.get(NotifierTarget, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notifier not found")
    error = await test_target(session, target)
    return {"ok": "false" if error else "true", "error": error}


def _hub_out(values: hubsettings.RuntimeSettings) -> HubSettingsOut:
    return HubSettingsOut(
        **vars(values),
        limits={field: list(bounds) for field, bounds in hubsettings.LIMITS.items()},
    )


@router.get("/hub", response_model=HubSettingsOut)
async def get_hub_settings(_: CurrentUser, session: SessionDep) -> HubSettingsOut:
    return _hub_out(await hubsettings.load(session))


@router.put("/hub", response_model=HubSettingsOut)
async def put_hub_settings(
    payload: HubSettingsUpdate, _: CurrentUser, session: SessionDep
) -> HubSettingsOut:
    """Timers and limits take effect on the next worker cycle — no restart needed."""
    return _hub_out(await hubsettings.update(session, payload.model_dump(exclude_unset=True)))
