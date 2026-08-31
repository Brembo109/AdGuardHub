"""Aggregation of live data across instances, for the AdGuard-compatible API.

Configuration is read from the hub's own state; anything that only exists on a
running resolver — counters, top lists, response times — has to be collected from
the instances and folded together.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from sqlalchemy import select

from ..adapters import AdapterError, build_adapter
from ..db import session_scope
from ..models import Instance
from ..runtime import get_crypto

logger = logging.getLogger(__name__)

# Plain sums.
COUNTERS = (
    "num_dns_queries",
    "num_blocked_filtering",
    "num_replaced_safebrowsing",
    "num_replaced_safesearch",
    "num_replaced_parental",
)
# Element-wise sums of the per-interval series AdGuard's charts use.
SERIES = (
    "dns_queries",
    "blocked_filtering",
    "replaced_safebrowsing",
    "replaced_parental",
)
# name -> count maps, summed per key.
TOP_LISTS = ("top_queried_domains", "top_clients", "top_blocked_domains", "top_upstreams_responses")


def _merge_series(into: list[int], addition: list[Any]) -> list[int]:
    """Sum two series position-wise, tolerating different lengths."""
    if not into:
        return [int(value or 0) for value in addition]
    length = max(len(into), len(addition))
    merged = []
    for index in range(length):
        left = into[index] if index < len(into) else 0
        right = addition[index] if index < len(addition) else 0
        merged.append(int(left or 0) + int(right or 0))
    return merged


def _merge_top(into: dict[str, int], addition: list[Any]) -> None:
    """AdGuard reports top lists as [{name: count}, …]."""
    for entry in addition or []:
        if not isinstance(entry, dict):
            continue
        for name, count in entry.items():
            try:
                into[name] = into.get(name, 0) + int(count)
            except (TypeError, ValueError):
                continue


def _as_top_list(counts: dict[str, int], limit: int = 20) -> list[dict[str, int]]:
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{name: count} for name, count in ranked]


async def aggregate_stats() -> dict[str, Any]:
    """Sum every reachable instance's statistics into one AdGuard-shaped document.

    An unreachable instance is skipped rather than failing the request: partial
    numbers are more useful to a phone app than an error.
    """
    async with session_scope() as session:
        result = await session.execute(select(Instance).where(Instance.enabled.is_(True)))
        instances = list(result.scalars().all())

    crypto = get_crypto()
    totals = dict.fromkeys(COUNTERS, 0)
    series: dict[str, list[int]] = {key: [] for key in SERIES}
    tops: dict[str, dict[str, int]] = {key: {} for key in TOP_LISTS}
    weighted_time = 0.0
    weight = 0
    time_units = "hours"
    contributing = 0

    for instance in instances:
        adapter = build_adapter(instance, crypto)
        try:
            data = await adapter.stats()
        except (AdapterError, ValueError) as exc:
            logger.debug("Stats unavailable from %s: %s", instance.name, exc)
            continue
        finally:
            await adapter.aclose()

        contributing += 1
        for key in COUNTERS:
            with contextlib.suppress(TypeError, ValueError):
                totals[key] += int(data.get(key) or 0)
        for key in SERIES:
            value = data.get(key)
            if isinstance(value, list):
                series[key] = _merge_series(series[key], value)
        for key in TOP_LISTS:
            _merge_top(tops[key], data.get(key))
        if data.get("time_units"):
            time_units = str(data["time_units"])

        # Average processing time is meaningless summed; weight it by query count.
        queries = int(data.get("num_dns_queries") or 0)
        with contextlib.suppress(TypeError, ValueError):
            weighted_time += float(data.get("avg_processing_time") or 0) * queries
        weight += queries

    return {
        **totals,
        **series,
        **{key: _as_top_list(counts) for key, counts in tops.items()},
        "avg_processing_time": (weighted_time / weight) if weight else 0,
        "time_units": time_units,
        # Not part of AdGuard's own document; harmless to clients and useful when
        # the numbers look lower than expected because a node was down.
        "adguardhub_instances_reporting": contributing,
        "adguardhub_instances_total": len(instances),
    }
