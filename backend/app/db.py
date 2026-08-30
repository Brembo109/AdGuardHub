"""Async SQLAlchemy engine/session wiring."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings
from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class DataDirError(RuntimeError):
    """The data directory is missing or not writable by the current user."""


def check_data_dir() -> None:
    """Fail fast, and in plain language, when the data directory is unusable.

    Without this, an unwritable bind mount surfaces as a bare "unable to open
    database file" under a hundred lines of SQLAlchemy traceback, which says
    nothing about the actual problem: the directory's ownership.
    """
    settings = get_settings()
    data_dir = settings.data_dir
    identity = f"uid={os.getuid()} gid={os.getgid()}"

    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError as exc:
        raise DataDirError(
            f"Cannot create the data directory {data_dir!r} as {identity}: {exc}. "
            "In Docker, set PUID/PGID to the user that owns the mounted directory "
            "(Unraid: PUID=99, PGID=100), or chown it on the host."
        ) from exc

    probe = os.path.join(data_dir, ".adguardhub-write-test")
    try:
        with open(probe, "w"):
            pass
        os.unlink(probe)
    except OSError as exc:
        raise DataDirError(
            f"The data directory {data_dir!r} is not writable as {identity}: {exc}. "
            "In Docker, set PUID/PGID to the user that owns the mounted directory "
            "(Unraid: PUID=99, PGID=100), or chown it on the host."
        ) from exc


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        os.makedirs(settings.data_dir, exist_ok=True)
        _engine = create_async_engine(settings.database_url, future=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def init_db() -> None:
    check_data_dir()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for background workers, which have no request to hang off."""
    async with get_sessionmaker()() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_sessionmaker()() as session:
        yield session
