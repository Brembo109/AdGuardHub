"""Drift detection and auto-correction (spec §6).

Anything changed on an instance out-of-band — after downtime, or by someone using the
native UI despite §2 — is detected here, corrected, and written to the drift log. There
is no maintenance mode in v1: a correction is always applied, but never silently.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import AdapterError, RemoteFilterList, build_adapter
from ..db import session_scope
from ..models import DriftEvent, Instance, InstanceStatus, PayloadKind, utcnow
from ..runtime import get_crypto
from . import hubsettings
from .events import bus
from .notify import EVENT_INSTANCE_UNREACHABLE, EVENT_RECONCILE_FIX, notify
from .sync import desired_filter_lists, desired_rules, desired_sections, push_kind

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
        return [_normalise(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalise(item) for key, item in sorted(value.items())}
    return value


def diff_section(
    name: str, expected: dict[str, Any], actual: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Per-key differences for one section, or ``None`` when it matches.

    ``actual`` is ``None`` when the instance does not implement the section; that is
    not drift, just a capability difference, so it is reported without a correction.
    """
    if actual is None:
        return {"unsupported": True}
    changed = {
        key: {"expected": _normalise(value), "actual": _normalise(actual.get(key))}
        for key, value in expected.items()
        if _normalise(actual.get(key)) != _normalise(value)
    }
    return changed or None


def diff_settings(
    expected: dict[str, dict[str, Any]], actual: dict[str, dict[str, Any] | None]
) -> Difference | None:
    """Fold every managed section into one difference for the settings payload."""
    details: dict[str, Any] = {}
    unsupported: list[str] = []
    for name, wanted in expected.items():
        found = diff_section(name, wanted, actual.get(name))
        if found is None:
            continue
        if found.get("unsupported"):
            unsupported.append(name)
            continue
        details[name] = found

    if not details and not unsupported:
        return None

    parts = []
    if details:
        parts.append(f"{len(details)} section(s) differ: {', '.join(sorted(details))}")
    if unsupported:
        parts.append(f"not supported by this instance: {', '.join(sorted(unsupported))}")
    payload: dict[str, Any] = dict(details)
    if unsupported:
        payload["_unsupported"] = unsupported
    return Difference(PayloadKind.settings.value, "; ".join(parts), payload)


def is_correctable(difference: Difference) -> bool:
    """Whether pushing can actually resolve this difference.

    A settings difference that is only "the instance does not implement this area"
    cannot be pushed away, and must not be treated as drift.
    """
    if difference.payload_kind != PayloadKind.settings.value:
        return True
    return bool(set(difference.details) - {"_unsupported"})


async def reconcile_instance(
    session: AsyncSession, instance: Instance, *, apply_fixes: bool = True
) -> InstanceReport:
    report = InstanceReport(instance.id, instance.name, checked=False)
    if not instance.enabled:
        return report

    expected_sections = await desired_sections(session)
    adapter = build_adapter(instance, get_crypto())
    try:
        state = await adapter.pull_state(tuple(expected_sections))
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
    # /control/status is the cheapest call AdGuard has, and reconciliation is the
    # only thing that talks to every node on a timer. Without this the reported
    # version would only ever refresh when the operator pressed Test by hand.
    with contextlib.suppress(AdapterError, ValueError):
        instance.version = await adapter.check()

    candidates = [
        diff_rules(await desired_rules(session), state.rules),
        diff_filter_lists(await desired_filter_lists(session), state.filter_lists),
        diff_settings(expected_sections, state.sections),
    ]
    report.differences = [item for item in candidates if item is not None]

    correctable = [item for item in report.differences if is_correctable(item)]
    fixed: set[str] = set()
    if correctable and apply_fixes:
        try:
            for difference in correctable:
                await push_kind(session, adapter, PayloadKind(difference.payload_kind))
                fixed.add(difference.payload_kind)
            report.corrected = True
            instance.last_synced_at = utcnow()
        except (AdapterError, ValueError) as exc:
            report.error = str(exc)

    await adapter.aclose()

    for difference in report.differences:
        if not is_correctable(difference):
            # A section this AdGuard build does not implement is a standing capability
            # gap, not drift. Logging it would append the same entry on every run.
            continue
        session.add(
            DriftEvent(
                instance_id=instance.id,
                instance_name=instance.name,
                payload_kind=difference.payload_kind,
                summary=difference.summary,
                details=json.dumps(difference.details, default=str),
                # Per difference: a later push can fail after an earlier one succeeded.
                corrected=difference.payload_kind in fixed,
            )
        )
    await session.commit()

    if correctable:
        await bus.publish("drift", {"instance": instance.name, "report": asdict(report)})
        headline = "; ".join(difference.summary for difference in correctable)
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
    while not stop.is_set():
        settings = hubsettings.current()
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.reconcile_interval)
            return
        except TimeoutError:
            pass
        if not hubsettings.current().reconcile_enabled:
            continue
        try:
            async with session_scope() as session:
                await reconcile_all(session)
        except Exception:
            logger.exception("Reconciliation pass failed")
