"""Central state of the managed configuration sections, and snapshots of it.

A section is stored as an opaque JSON document so adding a new AdGuard setting
never needs a schema change here. Sections start unmanaged: nothing is pushed
until the operator adopts a master (or turns the section on), so AdGuardHub
cannot overwrite a node's DNS or TLS setup before it has anything to write.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.sections import SECTION_NAMES, SPEC_BY_NAME, push_guard
from ..models import ConfigSection, FilterList, ListKind, Rule, RuleKind, RuleOrigin


def loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, default=str)


async def all_sections(session: AsyncSession) -> dict[str, ConfigSection]:
    result = await session.execute(select(ConfigSection))
    return {row.name: row for row in result.scalars().all()}


async def get_section(session: AsyncSession, name: str) -> ConfigSection:
    if name not in SPEC_BY_NAME:
        raise KeyError(name)
    row = await session.get(ConfigSection, name)
    if row is None:
        row = ConfigSection(name=name, managed=False, data="{}")
        session.add(row)
        await session.commit()
    return row


async def set_section(
    session: AsyncSession,
    name: str,
    *,
    data: dict[str, Any] | None = None,
    managed: bool | None = None,
) -> ConfigSection:
    row = await get_section(session, name)
    if data is not None:
        row.data = dumps(data)
    if managed is not None:
        row.managed = managed
    await session.commit()
    return row


async def managed_sections(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """Sections that should be pushed, in the declared order.

    A section whose push would do damage rather than replicate (an incomplete TLS
    document, say) is left out — ``skipped_sections`` reports why.
    """
    rows = await all_sections(session)
    result: dict[str, dict[str, Any]] = {}
    for name in SECTION_NAMES:
        row = rows.get(name)
        if row is None or not row.managed:
            continue
        data = loads(row.data)
        if not data or push_guard(name, data):
            continue
        result[name] = data
    return result


async def skipped_sections(session: AsyncSession) -> dict[str, str]:
    """Managed sections that cannot safely be pushed, mapped to the reason."""
    rows = await all_sections(session)
    skipped: dict[str, str] = {}
    for name in SECTION_NAMES:
        row = rows.get(name)
        if row is None or not row.managed:
            continue
        data = loads(row.data)
        if not data:
            skipped[name] = "nothing imported for this section yet"
            continue
        reason = push_guard(name, data)
        if reason:
            skipped[name] = reason
    return skipped


# --------------------------------------------------------------------------
# Snapshots — the unit of version control
# --------------------------------------------------------------------------


async def build_snapshot(session: AsyncSession) -> dict[str, Any]:
    """Everything AdGuardHub manages, in a form that can be diffed and restored."""
    rules = (await session.execute(select(Rule).order_by(Rule.id.asc()))).scalars().all()
    lists = (
        (await session.execute(select(FilterList).order_by(FilterList.id.asc()))).scalars().all()
    )
    sections = await all_sections(session)
    return {
        "rules": [
            {
                "text": rule.text,
                "kind": rule.kind,
                "origin": rule.origin,
                "enabled": rule.enabled,
                "comment": rule.comment,
            }
            for rule in rules
        ],
        "filter_lists": [
            {"name": item.name, "url": item.url, "kind": item.kind, "enabled": item.enabled}
            for item in lists
        ],
        "sections": {
            name: {"managed": row.managed, "data": loads(row.data)}
            for name, row in sorted(sections.items())
        },
    }


async def restore_snapshot(session: AsyncSession, snapshot: dict[str, Any]) -> dict[str, int]:
    """Replace the central state with ``snapshot``. Instances follow on the next push."""
    from sqlalchemy import delete

    await session.execute(delete(Rule))
    await session.execute(delete(FilterList))
    await session.flush()

    seen_rules: set[str] = set()
    for entry in snapshot.get("rules") or []:
        text = str(entry.get("text") or "").strip()
        if not text or text in seen_rules:
            continue
        seen_rules.add(text)
        session.add(
            Rule(
                text=text,
                kind=str(entry.get("kind") or RuleKind.block.value),
                origin=str(entry.get("origin") or RuleOrigin.custom.value),
                enabled=bool(entry.get("enabled", True)),
                comment=str(entry.get("comment") or ""),
            )
        )

    seen_lists: set[tuple[str, str]] = set()
    for entry in snapshot.get("filter_lists") or []:
        url = str(entry.get("url") or "")
        kind = str(entry.get("kind") or ListKind.blocklist.value)
        if not url or (kind, url) in seen_lists:
            continue
        seen_lists.add((kind, url))
        session.add(
            FilterList(
                name=str(entry.get("name") or url),
                url=url,
                kind=kind,
                enabled=bool(entry.get("enabled", True)),
            )
        )

    stored = snapshot.get("sections") or {}
    for name in SECTION_NAMES:
        entry = stored.get(name)
        row = await get_section(session, name)
        if entry is None:
            # Absent from the snapshot: leave the section alone rather than wiping it.
            continue
        row.managed = bool(entry.get("managed"))
        row.data = dumps(entry.get("data") or {})

    await session.commit()
    return {
        "rules": len(seen_rules),
        "filter_lists": len(seen_lists),
        "sections": len(stored),
    }
