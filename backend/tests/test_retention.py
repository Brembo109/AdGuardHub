"""Caps on the two operational logs that used to grow without bound.

Neither grows fast: rows appear when something goes wrong, so a healthy hub
barely accumulates any. The problem was that nothing in the design ever stopped
a flapping node from filling them over months.

The property that matters most is the one about the retry queue. A pending job
is work still owed to an instance, and pruning one would drop a change that
never reached a node — the exact failure the queue exists to prevent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db import session_scope
from app.models import DriftEvent, Instance, JobStatus, PushJob
from app.services import retention


async def _instance() -> int:
    async with session_scope() as session:
        row = Instance(name="node-a", base_url="http://node-a.test")
        session.add(row)
        await session.commit()
        return int(row.id)


async def _count(model: type, *conditions) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.count()).select_from(model).where(*conditions)
        )
        return int(result.scalar_one())


@pytest.mark.usefixtures("fresh_db")
async def test_drift_events_are_capped() -> None:
    instance_id = await _instance()
    async with session_scope() as session:
        for index in range(retention.MAX_DRIFT_EVENTS + 40):
            session.add(
                DriftEvent(
                    instance_id=instance_id,
                    instance_name="node-a",
                    payload_kind="settings",
                    summary=f"difference {index}",
                    details="{}",
                    corrected=True,
                )
            )
        await session.commit()

    async with session_scope() as session:
        removed = await retention.prune_drift_events(session)

    assert removed == 40
    assert await _count(DriftEvent) == retention.MAX_DRIFT_EVENTS


@pytest.mark.usefixtures("fresh_db")
async def test_the_newest_drift_events_are_the_ones_kept() -> None:
    """Trimming the wrong end would leave a log of only ancient problems."""
    instance_id = await _instance()
    async with session_scope() as session:
        for index in range(retention.MAX_DRIFT_EVENTS + 5):
            session.add(
                DriftEvent(
                    instance_id=instance_id,
                    instance_name="node-a",
                    payload_kind="settings",
                    summary=f"difference {index}",
                    details="{}",
                    corrected=True,
                )
            )
        await session.commit()
        await retention.prune_drift_events(session)

    async with session_scope() as session:
        newest = (
            await session.execute(select(DriftEvent).order_by(DriftEvent.id.desc()).limit(1))
        ).scalars().first()
        oldest = (
            await session.execute(select(DriftEvent).order_by(DriftEvent.id.asc()).limit(1))
        ).scalars().first()
    assert newest is not None and oldest is not None
    assert newest.summary == f"difference {retention.MAX_DRIFT_EVENTS + 4}"
    assert oldest.summary == "difference 5"


@pytest.mark.usefixtures("fresh_db")
async def test_applied_jobs_are_capped() -> None:
    instance_id = await _instance()
    async with session_scope() as session:
        for _ in range(retention.MAX_APPLIED_JOBS + 25):
            session.add(
                PushJob(
                    instance_id=instance_id,
                    payload_kind="rules",
                    status=JobStatus.applied.value,
                )
            )
        await session.commit()
        removed = await retention.prune_applied_jobs(session)

    assert removed == 25
    assert await _count(PushJob) == retention.MAX_APPLIED_JOBS


@pytest.mark.usefixtures("fresh_db")
async def test_the_retry_queue_is_never_pruned() -> None:
    """Pending and failed jobs are owed work, not history.

    They are also unbounded in principle — one per instance and payload kind —
    but that ceiling is the fleet size, and dropping one would silently abandon a
    change that never reached a node.
    """
    instance_id = await _instance()
    async with session_scope() as session:
        for _ in range(retention.MAX_APPLIED_JOBS + 50):
            session.add(
                PushJob(
                    instance_id=instance_id,
                    payload_kind="rules",
                    status=JobStatus.applied.value,
                )
            )
        for status in (JobStatus.pending, JobStatus.failed):
            session.add(
                PushJob(instance_id=instance_id, payload_kind="settings", status=status.value)
            )
        await session.commit()
        await retention.prune_applied_jobs(session)

    assert await _count(PushJob, PushJob.status == JobStatus.applied.value) == (
        retention.MAX_APPLIED_JOBS
    )
    assert await _count(PushJob, PushJob.status == JobStatus.pending.value) == 1
    assert await _count(PushJob, PushJob.status == JobStatus.failed.value) == 1


@pytest.mark.usefixtures("fresh_db")
async def test_pruning_under_the_cap_does_nothing() -> None:
    instance_id = await _instance()
    async with session_scope() as session:
        session.add(
            DriftEvent(
                instance_id=instance_id,
                instance_name="node-a",
                payload_kind="settings",
                summary="one",
                details="{}",
                corrected=True,
            )
        )
        await session.commit()
        assert await retention.prune_drift_events(session) == 0
        assert await retention.prune_applied_jobs(session) == 0

    assert await _count(DriftEvent) == 1


@pytest.mark.usefixtures("fresh_db")
async def test_an_empty_table_is_not_a_special_case() -> None:
    async with session_scope() as session:
        assert await retention.prune_drift_events(session) == 0
        assert await retention.prune_applied_jobs(session) == 0
