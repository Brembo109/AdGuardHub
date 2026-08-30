"""Dynamic instance management (spec §8) and initial import (spec §7)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..adapters import AdapterError, available_adapters, build_adapter
from ..deps import CurrentUser, SessionDep
from ..models import Instance, InstanceStatus, PushJob
from ..runtime import get_crypto
from ..schemas import ImportRequest, InstanceCreate, InstanceOut, InstanceUpdate
from ..services.importer import import_from_instance
from ..services.sync import ALL_KINDS, check_instance, push_to_instance, schedule_sync

router = APIRouter(prefix="/api/instances", tags=["instances"])


def to_out(instance: Instance) -> InstanceOut:
    return InstanceOut(
        id=instance.id,
        name=instance.name,
        base_url=instance.base_url,
        adapter=instance.adapter,
        username=instance.username,
        has_password=bool(instance.password_encrypted),
        verify_tls=instance.verify_tls,
        enabled=instance.enabled,
        status=instance.status,
        last_error=instance.last_error,
        last_seen_at=instance.last_seen_at,
        last_synced_at=instance.last_synced_at,
        created_at=instance.created_at,
    )


async def _get(session: SessionDep, instance_id: int) -> Instance:
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
    return instance


@router.get("/adapters")
async def list_adapters(_: CurrentUser) -> list[str]:
    return available_adapters()


@router.get("", response_model=list[InstanceOut])
async def list_instances(_: CurrentUser, session: SessionDep) -> list[InstanceOut]:
    result = await session.execute(select(Instance).order_by(Instance.id.asc()))
    return [to_out(instance) for instance in result.scalars().all()]


@router.post("", response_model=InstanceOut, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: InstanceCreate, _: CurrentUser, session: SessionDep
) -> InstanceOut:
    if payload.adapter not in available_adapters():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown adapter")
    instance = Instance(
        name=payload.name,
        base_url=payload.base_url,
        adapter=payload.adapter,
        username=payload.username,
        password_encrypted=get_crypto().encrypt(payload.password) if payload.password else "",
        verify_tls=payload.verify_tls,
        enabled=payload.enabled,
        status=InstanceStatus.unknown.value
        if payload.enabled
        else InstanceStatus.disabled.value,
    )
    session.add(instance)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An instance with that name exists") from exc
    await check_instance(session, instance)
    return to_out(instance)


@router.patch("/{instance_id}", response_model=InstanceOut)
async def update_instance(
    instance_id: int, payload: InstanceUpdate, _: CurrentUser, session: SessionDep
) -> InstanceOut:
    instance = await _get(session, instance_id)
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(instance, field, value)
    if password is not None:
        instance.password_encrypted = get_crypto().encrypt(password) if password else ""
    if "enabled" in data:
        instance.status = (
            InstanceStatus.unknown.value if instance.enabled else InstanceStatus.disabled.value
        )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An instance with that name exists") from exc
    if instance.enabled:
        await check_instance(session, instance)
    return to_out(instance)


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_instance(instance_id: int, _: CurrentUser, session: SessionDep) -> None:
    instance = await _get(session, instance_id)
    jobs = await session.execute(select(PushJob).where(PushJob.instance_id == instance_id))
    for job in jobs.scalars().all():
        await session.delete(job)
    await session.delete(instance)
    await session.commit()


@router.post("/{instance_id}/test")
async def test_instance(instance_id: int, _: CurrentUser, session: SessionDep) -> dict[str, str]:
    """Probe connectivity and credentials without changing anything on the instance."""
    instance = await _get(session, instance_id)
    adapter = build_adapter(instance, get_crypto())
    try:
        version = await adapter.check()
    except (AdapterError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        await adapter.aclose()
    instance.status = InstanceStatus.online.value
    instance.last_error = ""
    await session.commit()
    return {"ok": "true", "version": version}


@router.post("/{instance_id}/push")
async def push_instance(instance_id: int, _: CurrentUser, session: SessionDep) -> dict[str, str]:
    """Force a full-state push to a single instance."""
    instance = await _get(session, instance_id)
    error = await push_to_instance(session, instance, ALL_KINDS, "manual push")
    return {"ok": "false" if error else "true", "error": error}


@router.post("/{instance_id}/import")
async def import_instance(
    instance_id: int, payload: ImportRequest, _: CurrentUser, session: SessionDep
) -> dict[str, object]:
    """Adopt this instance's configuration as the hub's state (spec §7)."""
    instance = await _get(session, instance_id)
    try:
        result = await import_from_instance(
            session, instance, replace=payload.replace, include_dns=payload.include_dns
        )
    except (AdapterError, ValueError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if payload.push_after_import:
        schedule_sync(ALL_KINDS, f"initial import from {instance.name}")
    return asdict(result)
