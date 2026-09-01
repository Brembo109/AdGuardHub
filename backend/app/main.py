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
from .models import User
from .runtime import using_ephemeral_secret
from .security import hash_password
from .services import hubsettings
from .services.querylog import querylog_worker
from .services.reconcile import reconcile_worker
from .services.sync import retry_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("adguardhub")

def build_version() -> str:
    """The release this build was cut from.

    The Release workflow passes the git tag into the image build, which bakes it
    in as ADGUARDHUB_VERSION. Nothing in the source tree carries a number, so a
    version here can never drift out of step with the tags the way a hand-edited
    constant does — and a build that came from no tag says so rather than
    claiming to be the last release someone happened to write down.
    """
    return os.environ.get("ADGUARDHUB_VERSION", "").strip() or "dev"


VERSION = build_version()


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
    if using_ephemeral_secret():
        logger.warning(
            "ADGUARDHUB_SECRET_KEY is not set. A random key is being used, so sessions and "
            "stored instance credentials will NOT survive a restart. Set it before real use."
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
