"""Async SQLAlchemy engine/session wiring."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings
from .models import Base

logger = logging.getLogger("adguardhub")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


_REMEDY = (
    "In Docker, set PUID/PGID to the user that owns the mounted directory "
    "(Unraid: PUID=99, PGID=100), or chown it on the host."
)


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
            f"Cannot create the data directory {data_dir!r} as {identity}: {exc}. {_REMEDY}"
        ) from exc

    probe = os.path.join(data_dir, ".adguardhub-write-test")
    try:
        with open(probe, "w"):
            pass
        os.unlink(probe)
    except OSError as exc:
        raise DataDirError(
            f"The data directory {data_dir!r} is not writable as {identity}: {exc}. "
            f"{_REMEDY}"
        ) from exc

    # A writable directory is not enough: a database left behind by an earlier run
    # under a different uid stays unwritable, and SQLite reports that identically.
    database = settings.database_path
    if os.path.exists(database):
        try:
            with open(database, "r+b"):
                pass
        except OSError as exc:
            raise DataDirError(
                f"The database {database!r} exists but is not writable as {identity}: {exc}. "
                "It was probably created by an earlier run under a different user. "
                f"{_REMEDY}"
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


def _add_missing_columns(connection) -> None:
    """Bring an existing database up to the current model, additively.

    ``create_all`` creates missing tables but never touches an existing one, so a
    new column would leave every running installation querying a column its
    database does not have. This adds them.

    Deliberately limited to additive changes with a default or NULL — the ones
    that make up almost every schema change here. A rename, a type change or a
    new constraint still needs a real migration, and would have to be written by
    hand; this is not a substitute for that.
    """
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                logger.warning(
                    "Cannot add column %s.%s automatically: it is NOT NULL with no default",
                    table.name,
                    column.name,
                )
                continue
            ddl = column.type.compile(connection.dialect)
            default = ""
            if column.default is not None and not callable(column.default.arg):
                literal = column.default.arg
                if isinstance(literal, str):
                    default = f" DEFAULT '{literal}'"
                elif isinstance(literal, bool):
                    default = f" DEFAULT {int(literal)}"
                elif isinstance(literal, (int, float)):
                    default = f" DEFAULT {literal}"
            connection.execute(
                text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl}{default}")
            )
            logger.info("Added missing column %s.%s", table.name, column.name)


async def init_db() -> None:
    check_data_dir()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


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
