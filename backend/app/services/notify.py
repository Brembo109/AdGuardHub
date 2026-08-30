"""Pluggable webhook notifications (spec §10)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import session_scope
from ..models import NotifierTarget
from .events import bus

logger = logging.getLogger(__name__)

# Events that can fire a notification. The UI offers these as checkboxes.
EVENT_RECONCILE_FIX = "reconcile.fixed"
EVENT_INSTANCE_UNREACHABLE = "instance.unreachable"
EVENT_PUSH_FAILED = "push.failed"

KNOWN_EVENTS = (EVENT_RECONCILE_FIX, EVENT_INSTANCE_UNREACHABLE, EVENT_PUSH_FAILED)
NOTIFIER_TYPES = ("homeassistant", "discord", "gotify")


def build_payload(target: NotifierTarget, event: str, title: str, message: str) -> dict[str, Any]:
    """Shape one notification for the target's specific webhook contract."""
    if target.type == "discord":
        return {"content": f"**{title}**\n{message}"}
    if target.type == "gotify":
        return {"title": title, "message": message, "priority": 5}
    # Home Assistant webhook triggers accept arbitrary JSON, exposed as trigger.json.
    return {"event": event, "title": title, "message": message, "source": "adguardhub"}


def _request_kwargs(target: NotifierTarget, payload: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"json": payload}
    if target.type == "gotify" and target.token:
        kwargs["headers"] = {"X-Gotify-Key": target.token}
    elif target.token:
        kwargs["headers"] = {"Authorization": f"Bearer {target.token}"}
    return kwargs


def target_wants(target: NotifierTarget, event: str) -> bool:
    """An empty ``events`` list means "everything"."""
    selected = [item for item in (target.events or "").split(",") if item]
    return not selected or event in selected


async def send_to_target(
    client: httpx.AsyncClient, target: NotifierTarget, event: str, title: str, message: str
) -> str:
    """Deliver one notification. Returns an error string, or "" on success."""
    payload = build_payload(target, event, title, message)
    try:
        response = await client.post(target.url, **_request_kwargs(target, payload))
    except httpx.HTTPError as exc:
        return str(exc)
    if response.status_code >= 400:
        return f"HTTP {response.status_code}: {response.text.strip()[:160]}"
    return ""


async def notify(event: str, title: str, message: str) -> None:
    """Fan a notification out to every enabled target subscribed to ``event``.

    Never raises: a broken webhook must not take down a sync or reconcile run.
    """
    await bus.publish("notification", {"event": event, "title": title, "message": message})
    try:
        async with session_scope() as session:
            targets = list(
                (
                    await session.execute(
                        select(NotifierTarget).where(NotifierTarget.enabled.is_(True))
                    )
                )
                .scalars()
                .all()
            )
            wanted = [target for target in targets if target_wants(target, event)]
            if not wanted:
                return
            timeout = get_settings().http_timeout
            async with httpx.AsyncClient(timeout=timeout) as client:
                for target in wanted:
                    error = await send_to_target(client, target, event, title, message)
                    if error:
                        logger.warning("Notifier '%s' failed: %s", target.name, error)
                    target.last_error = error
            await session.commit()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Notification dispatch failed for event %s", event)


async def test_target(session: AsyncSession, target: NotifierTarget) -> str:
    timeout = get_settings().http_timeout
    async with httpx.AsyncClient(timeout=timeout) as client:
        error = await send_to_target(
            client,
            target,
            "test",
            "AdGuardHub test notification",
            f"Notifier '{target.name}' is wired up correctly.",
        )
    target.last_error = error
    await session.commit()
    return error
