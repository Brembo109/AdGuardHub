"""Notification targets (spec §10) and managed DNS settings (spec §3)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import CurrentUser, SessionDep
from ..models import NotifierTarget
from ..schemas import NotifierCreate, NotifierOut, NotifierUpdate
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
