"""Drift detection and auto-correction (spec §6).

Anything changed on an instance out-of-band — after downtime, or by someone using the
native UI despite §2 — is detected here, corrected, and written to the drift log. There
is no maintenance mode in v1: a correction is always applied, but never silently.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import AdapterError, RemoteFilterList, build_adapter
from ..config import get_settings
from ..db import session_scope
from ..models import DriftEvent, Instance, InstanceStatus, PayloadKind, utcnow
from ..runtime import get_crypto
from .events import bus
from .notify import EVENT_INSTANCE_UNREACHABLE, EVENT_RECONCILE_FIX, notify
from .sync import desired_dns, desired_filter_lists, desired_rules, push_kind

logger = logging.getLogger(__name__)

MAX_DETAIL_ITEMS = 25


@dataclass(slots=True)
class Difference:
    payload_kind: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InstanceReport:
    instance_id: int
    instance_name: str
    checked: bool
    error: str = ""
    differences: list[Difference] = field(default_factory=list)
    corrected: bool = False


def _trim(items: list[str]) -> list[str]:
    if len(items) <= MAX_DETAIL_ITEMS:
        return items
    return [*items[:MAX_DETAIL_ITEMS], f"… and {len(items) - MAX_DETAIL_ITEMS} more"]


def diff_rules(expected: list[str], actual: list[str]) -> Difference | None:
    if expected == actual:
        return None
    missing = _trim([rule for rule in expected if rule not in set(actual)])
    extra = _trim([rule for rule in actual if rule not in set(expected)])
    if missing or extra:
        summary = f"{len(missing)} rule(s) missing, {len(extra)} unexpected rule(s)"
    else:
        summary = "rules present but in a different order"
    return Difference(PayloadKind.rules.value, summary, {"missing": missing, "extra": extra})


def _list_key(item: RemoteFilterList) -> tuple[str, str]:
    return (item.kind, item.url)


def diff_filter_lists(
    expected: list[RemoteFilterList], actual: list[RemoteFilterList]
) -> Difference | None:
    expected_map = {_list_key(item): item for item in expected}
    actual_map = {_list_key(item): item for item in actual}
    missing = [f"{kind}:{url}" for kind, url in expected_map.keys() - actual_map.keys()]
    extra = [f"{kind}:{url}" for kind, url in actual_map.keys() - expected_map.keys()]
    changed = [
        f"{kind}:{url}"
        for (kind, url), item in expected_map.items()
        if (kind, url) in actual_map and actual_map[(kind, url)].enabled != item.enabled
    ]
    if not (missing or extra or changed):
        return None
    summary = (
        f"{len(missing)} subscription(s) missing, {len(extra)} unexpected, "
        f"{len(changed)} with a different enabled state"
    )
    return Difference(
        PayloadKind.filters.value,
        summary,
        {"missing": sorted(missing), "extra": sorted(extra), "changed": sorted(changed)},
    )


def _normalise(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item) for item in value]
    return value


def diff_dns(expected: dict[str, Any] | None, actual: dict[str, Any]) -> Difference | None:
    if expected is None:
        return None
    changed = {
        key: {"expected": _normalise(value), "actual": _normalise(actual.get(key))}
        for key, value in expected.items()
        if _normalise(actual.get(key)) != _normalise(value)
    }
    if not changed:
        return None
    return Difference(
        PayloadKind.dns.value,
        f"{len(changed)} DNS setting(s) differ: {', '.join(sorted(changed))}",
        changed,
    )


async def reconcile_instance(
    session: AsyncSession, instance: Instance, *, apply_fixes: bool = True
) -> InstanceReport:
    report = InstanceReport(instance.id, instance.name, checked=False)
    if not instance.enabled:
        return report

    adapter = build_adapter(instance, get_crypto())
    try:
        state = await adapter.pull_state()
    except (AdapterError, ValueError) as exc:
        await adapter.aclose()
        report.error = str(exc)
        was_online = instance.status == InstanceStatus.online.value
        instance.status = InstanceStatus.unreachable.value
        instance.last_error = report.error
        await session.commit()
        if was_online:
            await notify(
                EVENT_INSTANCE_UNREACHABLE,
                f"{instance.name} is unreachable",
                f"Reconciliation could not reach {instance.base_url}: {exc}",
            )
        return report

    report.checked = True
    instance.status = InstanceStatus.online.value
    instance.last_error = ""
    instance.last_seen_at = utcnow()

    expected_dns = await desired_dns(session)
    candidates = [
        diff_rules(await desired_rules(session), state.rules),
        diff_filter_lists(await desired_filter_lists(session), state.filter_lists),
        diff_dns(expected_dns, state.dns),
    ]
    report.differences = [item for item in candidates if item is not None]

    if report.differences and apply_fixes:
        try:
            for difference in report.differences:
                await push_kind(session, adapter, PayloadKind(difference.payload_kind))
            report.corrected = True
            instance.last_synced_at = utcnow()
        except (AdapterError, ValueError) as exc:
            report.error = str(exc)

    await adapter.aclose()

    for difference in report.differences:
        session.add(
            DriftEvent(
                instance_id=instance.id,
                instance_name=instance.name,
                payload_kind=difference.payload_kind,
                summary=difference.summary,
                details=json.dumps(difference.details, default=str),
                corrected=report.corrected,
            )
        )
    await session.commit()

    if report.differences:
        await bus.publish("drift", {"instance": instance.name, "report": asdict(report)})
        headline = "; ".join(difference.summary for difference in report.differences)
        await notify(
            EVENT_RECONCILE_FIX,
            f"Drift {'corrected' if report.corrected else 'detected'} on {instance.name}",
            headline,
        )
    return report


async def reconcile_all(session: AsyncSession, *, apply_fixes: bool = True) -> list[InstanceReport]:
    result = await session.execute(
        select(Instance).where(Instance.enabled.is_(True)).order_by(Instance.id.asc())
    )
    reports = []
    for instance in result.scalars().all():
        reports.append(await reconcile_instance(session, instance, apply_fixes=apply_fixes))
    return reports


async def reconcile_worker(stop: asyncio.Event) -> None:  # pragma: no cover - background loop
    interval = get_settings().reconcile_interval
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            async with session_scope() as session:
                await reconcile_all(session)
        except Exception:
            logger.exception("Reconciliation pass failed")
