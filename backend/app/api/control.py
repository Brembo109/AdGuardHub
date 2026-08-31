"""AdGuard Home compatible API, so existing clients can talk to the hub.

Apps built for AdGuard Home — the iOS and Android remotes, scripts, Home Assistant
integrations — speak ``/control/*``. Pointing one at AdGuardHub instead of at a
single node makes it manage all of them at once, which is exactly the promise of
the hub.

The mapping is deliberate:

* configuration is answered from the hub's own state, not from any one node, so
  what a client reads is what the hub will enforce;
* writes go into the central model and are pushed like any other change, so an
  edit from a phone reaches every instance;
* live data that only a running resolver has — counters, top lists — is aggregated
  across the instances.

Authentication is the hub's own admin account and session cookie: this surface is
no more exposed than the web UI it sits beside.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from ..adapters.sections import SECTION_NAMES
from ..deps import CurrentUser, SessionDep
from ..models import FilterList, Instance, ListKind, PayloadKind, Rule
from ..schemas import ControlLogin
from ..security import verify_password
from ..services import versions as version_service
from ..services.aggregate import aggregate_stats
from ..services.config import get_section, loads, set_section
from ..services.hubsettings import current as current_settings
from ..services.querylog import buffer
from ..services.rules import classify, is_comment
from ..services.sync import schedule_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/control", tags=["adguard-compat"], include_in_schema=False)

RULE_KINDS = (PayloadKind.rules,)
LIST_KINDS = (PayloadKind.filters,)
SETTING_KINDS = (PayloadKind.settings,)


def _guard() -> None:
    if not current_settings().external_api_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The AdGuard-compatible API is switched off in AdGuardHub's settings.",
        )


async def _section(session: SessionDep, name: str) -> dict[str, Any]:
    return loads((await get_section(session, name)).data)


async def _write_section(
    session: SessionDep, name: str, changes: dict[str, Any], user: CurrentUser, label: str
) -> None:
    """Merge a partial change into a section and push it, as a UI edit would."""
    data = {**(await _section(session, name)), **changes}
    await set_section(session, name, data=data)
    await version_service.record(session, label, author=user.username)
    schedule_sync(SETTING_KINDS, label)


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------


@router.post("/login")
async def login(payload: ControlLogin, response: Response, session: SessionDep) -> dict[str, str]:
    """AdGuard's login, answered with the hub's own admin account."""
    _guard()
    from ..models import User
    from .auth import _set_cookie

    result = await session.execute(select(User).where(User.username == payload.name))
    user = result.scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid username or password")
    _set_cookie(response, user.username)
    return {}


@router.get("/logout")
@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    from ..config import get_settings

    response.delete_cookie(get_settings().session_cookie, path="/")
    return {}


# --------------------------------------------------------------------------
# Status and live data
# --------------------------------------------------------------------------


@router.get("/status")
async def status_endpoint(user: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    from ..main import VERSION

    dns = await _section(session, "dns")
    instances = (
        (await session.execute(select(Instance).where(Instance.enabled.is_(True))))
        .scalars()
        .all()
    )
    return {
        "version": f"AdGuardHub {VERSION}",
        "language": "en",
        "dns_addresses": [instance.base_url for instance in instances],
        "dns_port": 53,
        "protection_enabled": bool(dns.get("protection_enabled", True)),
        "protection_disabled_duration": 0,
        "running": True,
        # The hub does not serve DHCP and never syncs it.
        "dhcp_available": False,
    }


@router.get("/profile")
async def profile(user: CurrentUser) -> dict[str, Any]:
    _guard()
    return {"name": user.username, "language": "en", "theme": "auto"}


@router.get("/stats")
async def stats(_: CurrentUser) -> dict[str, Any]:
    _guard()
    return await aggregate_stats()


@router.get("/querylog")
async def querylog(
    _: CurrentUser,
    limit: int = Query(100, ge=1, le=2000),
    search: str = "",
    response_status: str = Query("", alias="response_status"),
) -> dict[str, Any]:
    """The aggregated log, in AdGuard's own shape.

    Each entry keeps the instance name in ``client_info``, so a client that shows it
    can tell which node answered.
    """
    _guard()
    entries = await buffer.snapshot(
        limit, search=search, blocked_only=response_status == "blocked"
    )
    return {
        "data": [
            {
                "time": entry["time"],
                "question": {
                    "name": entry["question"],
                    "type": entry["question_type"] or "A",
                    "class": "IN",
                },
                "client": entry["client"],
                "client_info": {"name": entry["instance"]},
                "reason": entry["answer_status"] or "NotFilteredNotFound",
                "rules": [{"text": entry["rule"]}] if entry["rule"] else [],
                "elapsed_ms": str(entry["elapsed_ms"]),
                "upstream": entry["upstream"],
                "answer": [],
            }
            for entry in entries
        ],
        "oldest": entries[-1]["time"] if entries else "",
    }


# --------------------------------------------------------------------------
# Filtering: rules and subscriptions
# --------------------------------------------------------------------------


@router.get("/filtering/status")
async def filtering_status(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    config = await _section(session, "filtering_config")
    rules = (
        (await session.execute(select(Rule).where(Rule.enabled.is_(True)).order_by(Rule.id)))
        .scalars()
        .all()
    )
    lists = (
        (await session.execute(select(FilterList).order_by(FilterList.id))).scalars().all()
    )

    def serialise(item: FilterList) -> dict[str, Any]:
        return {
            "id": item.id,
            "enabled": item.enabled,
            "url": item.url,
            "name": item.name,
            "rules_count": 0,
            "last_updated": "",
        }

    return {
        "enabled": bool(config.get("enabled", True)),
        "interval": config.get("interval", 24),
        "user_rules": [rule.text for rule in rules],
        "filters": [serialise(item) for item in lists if item.kind == ListKind.blocklist.value],
        "whitelist_filters": [
            serialise(item) for item in lists if item.kind == ListKind.allowlist.value
        ],
    }


@router.post("/filtering/set_rules")
async def set_rules(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    """Replace the hub's rule set, exactly as the native UI's editor would."""
    _guard()
    from sqlalchemy import delete

    from ..models import RuleOrigin

    incoming = [str(line).strip() for line in payload.get("rules") or []]
    await session.execute(delete(Rule))
    await session.flush()
    seen: set[str] = set()
    for text in incoming:
        if not text or is_comment(text) or text in seen:
            continue
        seen.add(text)
        session.add(
            Rule(text=text, kind=classify(text).value, origin=RuleOrigin.custom.value)
        )
    await session.commit()

    label = f"rules replaced via the AdGuard API ({len(seen)} rule(s))"
    await version_service.record(session, label, author=user.username)
    schedule_sync(RULE_KINDS, label)
    return {}


@router.post("/filtering/config")
async def filtering_config(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    changes = {key: payload[key] for key in ("enabled", "interval") if key in payload}
    await _write_section(
        session, "filtering_config", changes, user, "filtering config changed via the AdGuard API"
    )
    return {}


@router.post("/filtering/add_url")
async def add_url(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    url = str(payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "url is required")
    kind = ListKind.allowlist.value if payload.get("whitelist") else ListKind.blocklist.value

    existing = (
        await session.execute(
            select(FilterList).where(FilterList.url == url, FilterList.kind == kind)
        )
    ).scalars().first()
    if existing is None:
        session.add(
            FilterList(name=str(payload.get("name") or url), url=url, kind=kind, enabled=True)
        )
        await session.commit()

    label = f"subscription added via the AdGuard API: {url}"
    await version_service.record(session, label, author=user.username)
    schedule_sync(LIST_KINDS, label)
    return {}


@router.post("/filtering/remove_url")
async def remove_url(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    url = str(payload.get("url") or "")
    kind = ListKind.allowlist.value if payload.get("whitelist") else ListKind.blocklist.value
    item = (
        await session.execute(
            select(FilterList).where(FilterList.url == url, FilterList.kind == kind)
        )
    ).scalars().first()
    if item is not None:
        await session.delete(item)
        await session.commit()
        label = f"subscription removed via the AdGuard API: {url}"
        await version_service.record(session, label, author=user.username)
        schedule_sync(LIST_KINDS, label)
    return {}


@router.post("/filtering/set_url")
async def set_url(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    url = str(payload.get("url") or "")
    kind = ListKind.allowlist.value if payload.get("whitelist") else ListKind.blocklist.value
    data = payload.get("data") or {}
    item = (
        await session.execute(
            select(FilterList).where(FilterList.url == url, FilterList.kind == kind)
        )
    ).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such subscription")
    if "enabled" in data:
        item.enabled = bool(data["enabled"])
    if data.get("name"):
        item.name = str(data["name"])
    await session.commit()

    label = f"subscription updated via the AdGuard API: {url}"
    await version_service.record(session, label, author=user.username)
    schedule_sync(LIST_KINDS, label)
    return {}


@router.post("/filtering/refresh")
async def refresh_filters(_: CurrentUser) -> dict[str, int]:
    """The hub tracks subscription URLs, not their contents — nothing to refresh here."""
    _guard()
    return {"updated": 0}


# --------------------------------------------------------------------------
# Protection and the toggle modules
# --------------------------------------------------------------------------


@router.post("/protection")
async def protection(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    """Pause or resume filtering everywhere at once."""
    _guard()
    await _write_section(
        session,
        "dns",
        {"protection_enabled": bool(payload.get("enabled"))},
        user,
        "protection {} via the AdGuard API".format(
            "enabled" if payload.get("enabled") else "disabled"
        ),
    )
    return {}


def _toggle_routes(name: str, path: str) -> None:
    @router.get(f"/{path}/status", name=f"{name}_status")
    async def read(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
        _guard()
        return {"enabled": bool((await _section(session, name)).get("enabled"))}

    @router.post(f"/{path}/enable", name=f"{name}_enable")
    async def enable(user: CurrentUser, session: SessionDep) -> dict[str, str]:
        _guard()
        await _write_section(
            session, name, {"enabled": True}, user, f"{path} enabled via the AdGuard API"
        )
        return {}

    @router.post(f"/{path}/disable", name=f"{name}_disable")
    async def disable(user: CurrentUser, session: SessionDep) -> dict[str, str]:
        _guard()
        await _write_section(
            session, name, {"enabled": False}, user, f"{path} disabled via the AdGuard API"
        )
        return {}


_toggle_routes("safebrowsing", "safebrowsing")
_toggle_routes("parental", "parental")


@router.get("/safesearch/status")
async def safesearch_status(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    return await _section(session, "safesearch")


@router.put("/safesearch/settings")
async def safesearch_settings(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    await _write_section(
        session, "safesearch", payload, user, "safe search changed via the AdGuard API"
    )
    return {}


# --------------------------------------------------------------------------
# The remaining configuration sections
# --------------------------------------------------------------------------


@router.get("/dns_info")
async def dns_info(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    return await _section(session, "dns")


@router.post("/dns_config")
async def dns_config(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    await _write_section(
        session, "dns", payload, user, "DNS settings changed via the AdGuard API"
    )
    return {}


@router.get("/clients")
async def clients(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    data = await _section(session, "clients")
    return {"clients": data.get("clients") or [], "auto_clients": [], "supported_tags": []}


@router.get("/access/list")
async def access_list(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    return await _section(session, "access")


@router.post("/access/set")
async def access_set(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    await _write_section(
        session, "access", payload, user, "access list changed via the AdGuard API"
    )
    return {}


@router.get("/rewrite/list")
async def rewrite_list(_: CurrentUser, session: SessionDep) -> list[dict[str, Any]]:
    _guard()
    return list((await _section(session, "rewrites")).get("items") or [])


@router.post("/rewrite/add")
async def rewrite_add(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    items = list((await _section(session, "rewrites")).get("items") or [])
    entry = {"domain": payload.get("domain"), "answer": payload.get("answer")}
    if entry not in items:
        items.append(entry)
    await _write_section(
        session, "rewrites", {"items": items}, user, "rewrite added via the AdGuard API"
    )
    return {}


@router.post("/rewrite/delete")
async def rewrite_delete(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    entry = {"domain": payload.get("domain"), "answer": payload.get("answer")}
    items = [
        item for item in (await _section(session, "rewrites")).get("items") or [] if item != entry
    ]
    await _write_section(
        session, "rewrites", {"items": items}, user, "rewrite removed via the AdGuard API"
    )
    return {}


@router.get("/querylog/config")
async def querylog_config(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    return await _section(session, "querylog_config")


@router.get("/stats/config")
async def stats_config(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    return await _section(session, "stats_config")


@router.get("/blocked_services/get")
async def blocked_services(_: CurrentUser, session: SessionDep) -> dict[str, Any]:
    _guard()
    data = await _section(session, "blocked_services")
    return {"ids": data.get("ids") or [], "schedule": data.get("schedule") or {}}


@router.put("/blocked_services/update")
async def blocked_services_update(
    payload: dict[str, Any], user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    _guard()
    await _write_section(
        session, "blocked_services", payload, user, "blocked services changed via the AdGuard API"
    )
    return {}


@router.get("/adguardhub/sections")
async def sections_index(_: CurrentUser) -> dict[str, Any]:
    """Not part of AdGuard's API: says which areas this compatibility layer serves."""
    _guard()
    return {"sections": list(SECTION_NAMES)}


__all__ = ["router"]
