"""How many rules each subscription actually contains.

The hub deliberately does not store the contents of a blocklist — it tracks the
URL and whether it is enabled, and AdGuard Home downloads and parses the file
itself (spec §12). So the hub cannot answer "how big is this list?" from its own
database: the only place that number exists is on the nodes, as the
``rules_count`` AdGuard reports for each subscription it has fetched.

That has two consequences worth stating rather than hiding:

* **It needs a reachable node.** With every instance down, the sizes are simply
  unknown, and the interface says so rather than showing zeros.
* **Nodes can legitimately disagree.** They refresh on their own schedule, so one
  may have yesterday's copy of a list that grew overnight. The highest count is
  reported as the answer — a node that has not fetched a list yet reports 0, and
  a stale copy is smaller than a fresh one, so the maximum is the most recent
  size any node has actually seen — and every node's own number is kept beside
  it so a disagreement can be looked at rather than averaged away.

None of this feeds reconciliation. A count is an observation about a file, not
configuration the hub owns, so a difference in it is never drift.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from ..adapters import AdapterError, build_adapter
from ..db import session_scope
from ..models import FilterList, Instance
from ..runtime import get_crypto

logger = logging.getLogger(__name__)

# Sizes change only when a node refreshes its lists, which AdGuard does on an
# interval measured in hours. Holding the fan-out for a minute keeps an open
# Filter lists tab from polling every node for a number that cannot have moved.
CACHE_TTL = 60.0

_cache: tuple[float, FilterSizes] | None = None
_cache_lock = asyncio.Lock()


@dataclass(slots=True)
class InstanceCount:
    instance_id: int
    instance_name: str
    rules_count: int


@dataclass(slots=True)
class ListSize:
    url: str
    kind: str
    rules_count: int
    per_instance: list[InstanceCount] = field(default_factory=list)

    @property
    def agreed(self) -> bool:
        """Whether every node that answered reported the same size."""
        return len({item.rules_count for item in self.per_instance}) <= 1


@dataclass(slots=True)
class FilterSizes:
    lists: list[ListSize] = field(default_factory=list)
    total_rules: int = 0
    instances_reporting: int = 0
    instances_total: int = 0


async def collect() -> FilterSizes:
    """Ask every reachable instance for its subscription sizes and fold them together.

    Only subscriptions the hub knows about are reported: anything else on a node
    is drift for reconciliation to remove, and listing it here would give it a
    permanence it should not have.
    """
    async with session_scope() as session:
        instances = list(
            (
                await session.execute(select(Instance).where(Instance.enabled.is_(True)))
            ).scalars().all()
        )
        known = {
            (item.kind, item.url): item.enabled
            for item in (
                await session.execute(select(FilterList).order_by(FilterList.id.asc()))
            ).scalars().all()
        }

    crypto = get_crypto()
    counts: dict[tuple[str, str], list[InstanceCount]] = {}
    reporting = 0

    for instance in instances:
        adapter = build_adapter(instance, crypto)
        try:
            remote = await adapter.pull_filter_lists()
        except (AdapterError, ValueError) as exc:
            logger.debug("Filter list sizes unavailable from %s: %s", instance.name, exc)
            continue
        finally:
            await adapter.aclose()

        reporting += 1
        for item in remote:
            key = (item.kind, item.url)
            if key not in known:
                continue
            counts.setdefault(key, []).append(
                InstanceCount(instance.id, instance.name, item.rules_count)
            )

    sizes = [
        ListSize(
            url=url,
            kind=kind,
            rules_count=max(
                (entry.rules_count for entry in counts.get((kind, url), [])), default=0
            ),
            per_instance=counts.get((kind, url), []),
        )
        for kind, url in known
    ]

    # "Active" is the hub's enabled state, not a node's: a subscription the hub
    # has switched off is off everywhere as soon as the push lands, and counting
    # it would inflate the total by a list nothing is filtering against.
    total = sum(size.rules_count for size in sizes if known[(size.kind, size.url)])
    return FilterSizes(
        lists=sizes,
        total_rules=total,
        instances_reporting=reporting,
        instances_total=len(instances),
    )


async def cached() -> FilterSizes:
    """``collect()`` behind a TTL, with concurrent callers collapsed onto one fan-out."""
    global _cache
    now = time.monotonic()
    held = _cache
    if held is not None and now - held[0] < CACHE_TTL:
        return held[1]

    async with _cache_lock:
        held = _cache
        if held is not None and time.monotonic() - held[0] < CACHE_TTL:
            return held[1]
        data = await collect()
        _cache = (time.monotonic(), data)
        return data


def invalidate() -> None:
    """Drop the held result, so the next read reflects a changed subscription list."""
    global _cache
    _cache = None
