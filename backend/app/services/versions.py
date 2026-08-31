"""Version history of the central configuration.

Every change records a snapshot, so the operator can see what a sync actually
carried, compare any two points, and roll back to either. A rollback is itself
recorded, so it can be undone in turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConfigVersion
from .config import build_snapshot, restore_snapshot

# Keep history bounded; the DB is meant to stay small (spec §12).
MAX_VERSIONS = 200


async def record(
    session: AsyncSession, label: str, *, author: str = "", kind: str = "change"
) -> ConfigVersion | None:
    """Store a snapshot of the current state, unless it is identical to the last one.

    Pushes are full-state and fire on every edit, so without this check a version
    would be created for changes that changed nothing.
    """
    snapshot = await build_snapshot(session)
    encoded = json.dumps(snapshot, sort_keys=True, default=str)

    latest = (
        await session.execute(select(ConfigVersion).order_by(ConfigVersion.id.desc()).limit(1))
    ).scalars().first()
    if latest is not None and latest.snapshot == encoded:
        return None

    version = ConfigVersion(label=label[:255], author=author, kind=kind, snapshot=encoded)
    session.add(version)
    await session.commit()
    await prune(session)
    return version


async def prune(session: AsyncSession) -> int:
    counted = await session.execute(select(func.count()).select_from(ConfigVersion))
    total = int(counted.scalar_one())
    if total <= MAX_VERSIONS:
        return 0
    cutoff = (
        await session.execute(
            select(ConfigVersion.id).order_by(ConfigVersion.id.desc()).offset(MAX_VERSIONS).limit(1)
        )
    ).scalar_one_or_none()
    if cutoff is None:
        return 0
    await session.execute(delete(ConfigVersion).where(ConfigVersion.id <= cutoff))
    await session.commit()
    return total - MAX_VERSIONS


def decode(version: ConfigVersion) -> dict[str, Any]:
    try:
        value = json.loads(version.snapshot or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


async def get(session: AsyncSession, version_id: int) -> ConfigVersion | None:
    return await session.get(ConfigVersion, version_id)


async def latest(session: AsyncSession) -> ConfigVersion | None:
    result = await session.execute(select(ConfigVersion).order_by(ConfigVersion.id.desc()).limit(1))
    return result.scalars().first()


# --------------------------------------------------------------------------
# Diffing
# --------------------------------------------------------------------------


@dataclass
class ListDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _rule_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("text")): item for item in snapshot.get("rules") or []}


def _list_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{item.get('kind')}:{item.get('url')}": item for item in snapshot.get("filter_lists") or []
    }


def _entry_diff(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> ListDiff:
    diff = ListDiff(
        added=sorted(after.keys() - before.keys()),
        removed=sorted(before.keys() - after.keys()),
    )
    for key in sorted(before.keys() & after.keys()):
        if before[key] != after[key]:
            diff.changed.append({"key": key, "before": before[key], "after": after[key]})
    return diff


def diff_sections(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Per-section, per-key differences between two snapshots."""
    before_sections = before.get("sections") or {}
    after_sections = after.get("sections") or {}
    result: dict[str, dict[str, Any]] = {}

    for name in sorted(set(before_sections) | set(after_sections)):
        old = before_sections.get(name) or {}
        new = after_sections.get(name) or {}
        old_data = old.get("data") or {}
        new_data = new.get("data") or {}
        keys = sorted(set(old_data) | set(new_data))
        changes = {
            key: {"before": old_data.get(key), "after": new_data.get(key)}
            for key in keys
            if old_data.get(key) != new_data.get(key)
        }
        managed_change = bool(old.get("managed")) != bool(new.get("managed"))
        if changes or managed_change:
            entry: dict[str, Any] = {"keys": changes}
            if managed_change:
                entry["managed"] = {
                    "before": bool(old.get("managed")),
                    "after": bool(new.get("managed")),
                }
            result[name] = entry
    return result


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    rules = _entry_diff(_rule_map(before), _rule_map(after))
    lists = _entry_diff(_list_map(before), _list_map(after))
    sections = diff_sections(before, after)
    return {
        "rules": {"added": rules.added, "removed": rules.removed, "changed": rules.changed},
        "filter_lists": {
            "added": lists.added,
            "removed": lists.removed,
            "changed": lists.changed,
        },
        "sections": sections,
        "empty": rules.empty and lists.empty and not sections,
    }


def summarise(diff_result: dict[str, Any]) -> str:
    parts: list[str] = []
    for area in ("rules", "filter_lists"):
        entry = diff_result.get(area) or {}
        counts = [
            (len(entry.get("added") or []), "added"),
            (len(entry.get("removed") or []), "removed"),
            (len(entry.get("changed") or []), "changed"),
        ]
        detail = ", ".join(f"{count} {word}" for count, word in counts if count)
        if detail:
            parts.append(f"{area.replace('_', ' ')}: {detail}")
    sections = diff_result.get("sections") or {}
    if sections:
        parts.append(f"sections: {', '.join(sorted(sections))}")
    return "; ".join(parts) or "no changes"


async def restore(
    session: AsyncSession, version: ConfigVersion, *, author: str = ""
) -> dict[str, int]:
    """Roll the central state back to ``version`` and record the rollback itself."""
    snapshot = decode(version)
    counts = await restore_snapshot(session, snapshot)
    await record(
        session,
        f"rolled back to version {version.id} ({version.label})"[:255],
        author=author,
        kind="restore",
    )
    return counts
