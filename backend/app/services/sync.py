"""Instant push, retry queue and instance health (spec §6).

Every push is *full state*: AdGuardHub computes what an instance should look like
from the central DB and replaces the instance's managed config with it. That makes
pushes idempotent, lets the retry queue coalesce, and removes any need for merges.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import AdapterError, DnsAdapter, RemoteFilterList, build_adapter
from ..db import session_scope
from ..models import (
    FilterList,
    Instance,
    InstanceStatus,
    JobStatus,
    PayloadKind,
    PushJob,
    Rule,
    utcnow,
)
from ..runtime import get_crypto
from . import hubsettings
from .config import managed_sections
from .events import bus
from .notify import EVENT_INSTANCE_UNREACHABLE, EVENT_PUSH_FAILED, notify

logger = logging.getLogger(__name__)

ALL_KINDS: tuple[PayloadKind, ...] = (
    PayloadKind.rules,
    PayloadKind.filters,
    PayloadKind.settings,
)


# --------------------------------------------------------------------------
# Desired state
# --------------------------------------------------------------------------


async def desired_rules(session: AsyncSession) -> list[str]:
    """The rule text every instance should carry, in a stable order."""
    result = await session.execute(
        select(Rule).where(Rule.enabled.is_(True)).order_by(Rule.id.asc())
    )
    return [rule.text for rule in result.scalars().all()]


async def desired_filter_lists(session: AsyncSession) -> list[RemoteFilterList]:
    result = await session.execute(select(FilterList).order_by(FilterList.id.asc()))
    return [
        RemoteFilterList(name=item.name, url=item.url, enabled=item.enabled, kind=item.kind)
        for item in result.scalars().all()
    ]


async def desired_sections(session: AsyncSession) -> dict[str, dict]:
    """The configuration documents every instance should carry."""
    return await managed_sections(session)


# --------------------------------------------------------------------------
# Push
# --------------------------------------------------------------------------


async def push_kind(session: AsyncSession, adapter: DnsAdapter, kind: PayloadKind) -> None:
    if kind is PayloadKind.rules:
        await adapter.push_rules(await desired_rules(session))
    elif kind is PayloadKind.filters:
        await adapter.push_filter_lists(await desired_filter_lists(session))
    elif kind is PayloadKind.settings:
        for name, data in (await desired_sections(session)).items():
            try:
                await adapter.push_section(name, data)
            except AdapterError as exc:
                # Name the section: "settings failed" alone is not actionable.
                raise AdapterError(f"section {name!r}: {exc}", status=exc.status) from exc


async def push_to_instance(
    session: AsyncSession,
    instance: Instance,
    kinds: tuple[PayloadKind, ...],
    reason: str,
) -> str:
    """Push ``kinds`` to one instance. Returns an error string, or "" on success."""
    adapter = build_adapter(instance, get_crypto())
    try:
        for kind in kinds:
            await push_kind(session, adapter, kind)
    except (AdapterError, ValueError) as exc:
        error = str(exc)
        was_online = instance.status == InstanceStatus.online.value
        instance.status = InstanceStatus.unreachable.value
        instance.last_error = error
        for kind in kinds:
            await queue_job(session, instance, kind, reason, error)
        await session.commit()
        await bus.publish(
            "instance.status",
            {"id": instance.id, "name": instance.name, "status": instance.status, "error": error},
        )
        await notify(
            EVENT_PUSH_FAILED,
            f"Push to {instance.name} failed",
            f"{reason or 'Sync'} could not be applied: {error}. Queued for retry.",
        )
        if was_online:
            await notify(
                EVENT_INSTANCE_UNREACHABLE,
                f"{instance.name} is unreachable",
                f"AdGuardHub can no longer reach {instance.base_url}: {error}",
            )
        return error
    finally:
        await adapter.aclose()

    instance.status = InstanceStatus.online.value
    instance.last_error = ""
    instance.last_seen_at = utcnow()
    instance.last_synced_at = utcnow()
    for kind in kinds:
        await close_jobs(session, instance, kind)
    await session.commit()
    await bus.publish(
        "instance.status",
        {"id": instance.id, "name": instance.name, "status": instance.status, "error": ""},
    )
    return ""


async def sync_all(
    session: AsyncSession,
    kinds: tuple[PayloadKind, ...] = ALL_KINDS,
    reason: str = "",
) -> dict[str, str]:
    """Instant push to every enabled instance, best effort and without rollback.

    A failing instance never blocks the others: its work goes to the retry queue.
    """
    result = await session.execute(select(Instance).where(Instance.enabled.is_(True)))
    instances = list(result.scalars().all())
    errors: dict[str, str] = {}
    for instance in instances:
        error = await push_to_instance(session, instance, kinds, reason)
        if error:
            errors[instance.name] = error
    await bus.publish(
        "sync",
        {
            "reason": reason,
            "kinds": [kind.value for kind in kinds],
            "instances": len(instances),
            "failed": list(errors),
        },
    )
    return errors


def schedule_sync(kinds: tuple[PayloadKind, ...], reason: str) -> None:
    """Fire-and-forget push so an API request returns without waiting on the network."""

    async def _run() -> None:
        try:
            async with session_scope() as session:
                await sync_all(session, kinds, reason)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Background sync failed (%s)", reason)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


_background_tasks: set[asyncio.Task[None]] = set()


async def drain_background() -> None:
    """Wait for every in-flight ``schedule_sync`` task. Used on shutdown and in tests."""
    while _background_tasks:
        await asyncio.gather(*list(_background_tasks), return_exceptions=True)


# --------------------------------------------------------------------------
# Retry queue
# --------------------------------------------------------------------------


async def queue_job(
    session: AsyncSession, instance: Instance, kind: PayloadKind, reason: str, error: str
) -> PushJob:
    """Open (or update) the single outstanding job for this instance + payload kind."""
    result = await session.execute(
        select(PushJob).where(
            PushJob.instance_id == instance.id,
            PushJob.payload_kind == kind.value,
            PushJob.status != JobStatus.applied.value,
        )
    )
    job = result.scalars().first()
    if job is None:
        job = PushJob(instance_id=instance.id, payload_kind=kind.value, reason=reason)
        session.add(job)
    job.status = JobStatus.failed.value if error else JobStatus.pending.value
    # ``attempts`` only gets its column default at flush time, so a freshly added
    # job still has None here.
    job.attempts = (job.attempts or 0) + 1
    job.last_error = error
    job.updated_at = utcnow()
    if reason:
        job.reason = reason
    return job


async def close_jobs(session: AsyncSession, instance: Instance, kind: PayloadKind) -> None:
    """A successful full-state push satisfies any outstanding job of the same kind."""
    result = await session.execute(
        select(PushJob).where(
            PushJob.instance_id == instance.id,
            PushJob.payload_kind == kind.value,
            PushJob.status != JobStatus.applied.value,
        )
    )
    for job in result.scalars().all():
        job.status = JobStatus.applied.value
        job.last_error = ""
        job.updated_at = utcnow()


async def process_retry_queue(session: AsyncSession) -> int:
    """Retry every open job whose instance is enabled. Returns the number recovered."""
    result = await session.execute(
        select(PushJob, Instance)
        .join(Instance, Instance.id == PushJob.instance_id)
        .where(PushJob.status != JobStatus.applied.value, Instance.enabled.is_(True))
        .order_by(PushJob.id.asc())
    )
    rows = list(result.all())
    recovered = 0
    seen: set[tuple[int, str]] = set()
    for job, instance in rows:
        key = (instance.id, job.payload_kind)
        if key in seen:
            continue
        seen.add(key)
        error = await push_to_instance(
            session, instance, (PayloadKind(job.payload_kind),), job.reason or "retry"
        )
        if not error:
            recovered += 1
    if recovered:
        await bus.publish("retry", {"recovered": recovered})
    return recovered


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


async def check_instance(session: AsyncSession, instance: Instance) -> str:
    """Probe one instance and record its status. Returns an error string, or ""."""
    if not instance.enabled:
        instance.status = InstanceStatus.disabled.value
        await session.commit()
        return ""
    adapter = build_adapter(instance, get_crypto())
    try:
        await adapter.check()
    except (AdapterError, ValueError) as exc:
        was_online = instance.status == InstanceStatus.online.value
        instance.status = InstanceStatus.unreachable.value
        instance.last_error = str(exc)
        await session.commit()
        if was_online:
            await notify(
                EVENT_INSTANCE_UNREACHABLE,
                f"{instance.name} is unreachable",
                f"AdGuardHub can no longer reach {instance.base_url}: {exc}",
            )
        return str(exc)
    finally:
        await adapter.aclose()

    instance.status = InstanceStatus.online.value
    instance.last_error = ""
    instance.last_seen_at = datetime.now(UTC)
    await session.commit()
    return ""


async def retry_worker(stop: asyncio.Event) -> None:  # pragma: no cover - background loop
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=hubsettings.current().retry_interval)
            return
        except TimeoutError:
            pass
        try:
            async with session_scope() as session:
                await process_retry_queue(session)
        except Exception:
            logger.exception("Retry queue pass failed")
