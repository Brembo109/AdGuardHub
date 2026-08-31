"""Operational settings the operator can change without restarting the container.

The environment still supplies the defaults, but timers and limits belong in the UI:
changing how often reconciliation runs should not mean editing a compose file and
recreating the container.

Values are cached in the process because they are read from places that have no
database session — building an adapter, for one — and are refreshed whenever the
settings are written.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import HubSettings

logger = logging.getLogger(__name__)

# Guard rails, so a typo cannot hammer the instances or stall the hub entirely.
LIMITS: dict[str, tuple[int, int]] = {
    "reconcile_interval": (30, 86_400),
    "retry_interval": (10, 3_600),
    "querylog_poll_interval": (1, 3_600),
    "querylog_buffer_size": (100, 50_000),
    "http_timeout": (1, 120),
}


@dataclass
class RuntimeSettings:
    reconcile_enabled: bool
    reconcile_interval: int
    retry_interval: int
    querylog_enabled: bool
    querylog_poll_interval: int
    querylog_buffer_size: int
    http_timeout: int


def _from_env() -> RuntimeSettings:
    env = get_settings()
    return RuntimeSettings(
        reconcile_enabled=True,
        reconcile_interval=env.reconcile_interval,
        retry_interval=env.retry_interval,
        querylog_enabled=True,
        querylog_poll_interval=env.querylog_poll_interval,
        querylog_buffer_size=env.querylog_buffer_size,
        http_timeout=int(env.http_timeout),
    )


_cache: RuntimeSettings | None = None


def current() -> RuntimeSettings:
    """The values in force right now. Falls back to the environment before load."""
    return _cache if _cache is not None else _from_env()


def clamp(field: str, value: int) -> int:
    low, high = LIMITS[field]
    return max(low, min(high, int(value)))


async def load(session: AsyncSession) -> RuntimeSettings:
    """Read the stored settings, seeding them from the environment on first run."""
    global _cache
    row = await session.get(HubSettings, 1)
    if row is None:
        defaults = _from_env()
        row = HubSettings(id=1, **asdict(defaults))
        session.add(row)
        await session.commit()
    _cache = _to_runtime(row)
    return _cache


async def update(session: AsyncSession, changes: dict[str, object]) -> RuntimeSettings:
    global _cache
    row = await session.get(HubSettings, 1)
    if row is None:
        await load(session)
        row = await session.get(HubSettings, 1)
    assert row is not None

    for field, value in changes.items():
        if value is None:
            continue
        if field in LIMITS:
            setattr(row, field, clamp(field, int(value)))  # type: ignore[arg-type]
        elif field in {"reconcile_enabled", "querylog_enabled"}:
            setattr(row, field, bool(value))
    await session.commit()

    _cache = _to_runtime(row)
    _apply_side_effects(_cache)
    return _cache


def _to_runtime(row: HubSettings) -> RuntimeSettings:
    return RuntimeSettings(
        reconcile_enabled=row.reconcile_enabled,
        reconcile_interval=row.reconcile_interval,
        retry_interval=row.retry_interval,
        querylog_enabled=row.querylog_enabled,
        querylog_poll_interval=row.querylog_poll_interval,
        querylog_buffer_size=row.querylog_buffer_size,
        http_timeout=row.http_timeout,
    )


def _apply_side_effects(settings: RuntimeSettings) -> None:
    """Settings that own state elsewhere have to be pushed into it."""
    from .querylog import buffer

    buffer.resize(settings.querylog_buffer_size)
