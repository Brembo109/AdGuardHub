"""Aggregation of live data across instances, for the AdGuard-compatible API.

Configuration is read from the hub's own state; anything that only exists on a
running resolver — counters, top lists, response times — has to be collected from
the instances and folded together.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from sqlalchemy import select

from ..adapters import AdapterError, build_adapter
from ..db import session_scope
from ..models import Instance
from ..runtime import get_crypto

logger = logging.getLogger(__name__)

# Collecting statistics fans out to every node on every call. The dashboard polls,
# and a second browser tab doubles that, so the result is held briefly and shared.
# Short enough that the numbers still look live, long enough that leaving the page
# open does not become a load generator on the resolvers.
STATS_CACHE_TTL = 10.0

_cache: tuple[float, dict[str, Any]] | None = None
_cache_lock = asyncio.Lock()

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


async def cached_stats() -> dict[str, Any]:
    """``aggregate_stats()`` behind a short TTL, with concurrent callers collapsed.

    The lock matters as much as the TTL: without it, three tabs opening at once
    would each start their own fan-out before any of them stored a result.
    """
    global _cache
    now = time.monotonic()
    cached = _cache
    if cached is not None and now - cached[0] < STATS_CACHE_TTL:
        return cached[1]

    async with _cache_lock:
        # Another caller may have refreshed it while this one waited for the lock.
        cached = _cache
        now = time.monotonic()
        if cached is not None and now - cached[0] < STATS_CACHE_TTL:
            return cached[1]
        data = await aggregate_stats()
        _cache = (time.monotonic(), data)
        return data


def invalidate_stats_cache() -> None:
    """Drop the held result, so the next read reflects a changed instance list."""
    global _cache
    _cache = None


def _top(entries: Any, limit: int = 5) -> list[dict[str, Any]]:
    """AdGuard's ``[{name: count}, …]`` shape flattened for the UI."""
    out: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        for name, count in entry.items():
            out.append({"name": name, "count": int(count)})
        if len(out) >= limit:
            break
    return out[:limit]


async def traffic_summary() -> dict[str, Any]:
    """What the hub's own dashboard shows: totals, the two series, and top lists."""
    data = await cached_stats()
    queries = int(data.get("num_dns_queries") or 0)
    blocked = int(data.get("num_blocked_filtering") or 0)
    return {
        "queries": queries,
        "blocked": blocked,
        # Reported rather than recomputed in the browser, so every surface that
        # shows a block rate shows the same number.
        "block_rate": (blocked / queries * 100) if queries else 0.0,
        "replaced_safebrowsing": int(data.get("num_replaced_safebrowsing") or 0),
        # AdGuard reports this in seconds: a node whose own dashboard says 11 ms
        # sends 0.011. The hub used to pass it through and label it "ms", so the
        # dashboard read 0.011 ms — a thousandfold understatement that looked
        # plausible enough to go unnoticed. The unit is in the name now, because
        # the one thing this field cannot afford again is being ambiguous.
        #
        # Only the hub's own dashboard gets the converted value. /control/stats
        # serves cached_stats() unchanged, so a client built for AdGuard Home
        # still reads the seconds it expects.
        "avg_processing_time_ms": float(data.get("avg_processing_time") or 0) * 1000,
        "series_queries": [int(v) for v in data.get("dns_queries") or []],
        "series_blocked": [int(v) for v in data.get("blocked_filtering") or []],
        "time_units": str(data.get("time_units") or "hours"),
        "top_queried": _top(data.get("top_queried_domains")),
        "top_blocked": _top(data.get("top_blocked_domains")),
        "top_clients": _top(data.get("top_clients")),
        "instances_reporting": int(data.get("adguardhub_instances_reporting") or 0),
        "instances_total": int(data.get("adguardhub_instances_total") or 0),
    }
