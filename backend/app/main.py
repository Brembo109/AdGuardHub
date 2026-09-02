"""FastAPI application: API, background workers and the built frontend."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .api import auth, backup, blocklists, config, control, instances, ops, querylog, rules
from .api import settings as settings_api
from .config import get_settings
from .db import DataDirError, dispose_db, init_db, session_scope
from .deps import admin_exists
from .logging_setup import configure as configure_logging
from .models import User
from .runtime import using_ephemeral_secret
from .security import SecretKeyError, hash_password
from .services import hubsettings
from .services.querylog import querylog_worker
from .services.reconcile import reconcile_worker
from .services.sync import retry_worker
from .version import VERSION

_settings = get_settings()
configure_logging(
    _settings.log_level,
    log_file=_settings.log_file,
    max_bytes=_settings.log_file_max_bytes,
    backups=_settings.log_file_backups,
)
logger = logging.getLogger("adguardhub")


async def bootstrap_admin() -> None:
    """Create the admin account from the environment, if configured and none exists."""
    config = get_settings()
    if not (config.admin_username and config.admin_password):
        return
    async with session_scope() as session:
        if await admin_exists(session):
            existing = await session.execute(
                select(User).where(User.username == config.admin_username)
            )
            user = existing.scalars().first()
            if user is not None:
                user.password_hash = hash_password(config.admin_password)
                await session.commit()
            return
        session.add(
            User(
                username=config.admin_username,
                password_hash=hash_password(config.admin_password),
            )
        )
        await session.commit()
        logger.info("Created admin account '%s' from the environment", config.admin_username)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolved first, and deliberately not lazily: a refused key has to stop the
    # start here, with one readable line, rather than surfacing later as a 500 on
    # whichever request happened to need the crypto first.
    try:
        ephemeral = using_ephemeral_secret()
    except SecretKeyError as exc:
        logger.error("Startup aborted: %s", exc)
        raise
    if ephemeral:
        logger.warning(
            "No usable key store, so a random key is in use. Sessions and stored instance "
            "credentials will NOT survive a restart — see the warning above for why."
        )
    # Printed before anything can fail, so a pasted log always identifies the build
    # and the user it runs as — the two things a startup problem turns on.
    logger.info(
        "AdGuardHub %s starting as uid=%d gid=%d, data dir %s",
        VERSION,
        os.getuid(),
        os.getgid(),
        get_settings().data_dir,
    )
    try:
        await init_db()
    except DataDirError as exc:
        # Surface the remedy as a single readable line before uvicorn's traceback.
        logger.error("Startup aborted: %s", exc)
        raise
    await bootstrap_admin()
    # Seed the runtime settings from the environment, then let the UI own them.
    async with session_scope() as session:
        await hubsettings.load(session)

    stop = asyncio.Event()
    workers = [
        asyncio.create_task(retry_worker(stop), name="retry"),
        asyncio.create_task(reconcile_worker(stop), name="reconcile"),
        asyncio.create_task(querylog_worker(stop), name="querylog"),
    ]
    app.state.stop_event = stop
    try:
        yield
    finally:
        stop.set()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await dispose_db()


app = FastAPI(title="AdGuardHub", version=VERSION, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(instances.router)
app.include_router(rules.router)
app.include_router(blocklists.router)
app.include_router(querylog.router)
app.include_router(settings_api.router)
app.include_router(ops.router)
app.include_router(config.router)
app.include_router(config.versions_router)
app.include_router(backup.router)
# Registered before the SPA fallback so /control/* is not swallowed by it.
app.include_router(control.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


def mount_frontend(application: FastAPI) -> None:
    """Serve the built React app, falling back to index.html for client-side routes."""
    static_dir = get_settings().static_dir
    index = os.path.join(static_dir, "index.html")
    if not os.path.isfile(index):
        logger.info("No built frontend at %s — serving the API only", static_dir)
        return

    assets = os.path.join(static_dir, "assets")
    if os.path.isdir(assets):
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(path: str) -> FileResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = os.path.normpath(os.path.join(static_dir, path))
        if (
            path
            and os.path.isfile(candidate)
            and os.path.commonpath([os.path.abspath(static_dir), os.path.abspath(candidate)])
            == os.path.abspath(static_dir)
        ):
            return FileResponse(candidate)
        return FileResponse(index)


mount_frontend(app)
