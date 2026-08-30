"""Initial import from a chosen master instance (spec §7).

One instance's configuration is taken wholesale as the starting state; the others are
overwritten on the next push. There is no merge between instances, by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..models import DnsSettings, FilterList, Instance, Rule, RuleOrigin
from ..runtime import get_crypto
from .rules import classify, is_comment, normalise


@dataclass(slots=True)
class ImportResult:
    instance: str
    rules_imported: int
    rules_skipped: int
    filter_lists_imported: int
    dns_imported: bool
    replaced: bool


async def import_from_instance(
    session: AsyncSession,
    instance: Instance,
    *,
    replace: bool = True,
    include_dns: bool = False,
) -> ImportResult:
    adapter = build_adapter(instance, get_crypto())
    try:
        state = await adapter.pull_state()
    finally:
        await adapter.aclose()

    if replace:
        await session.execute(delete(Rule))
        await session.execute(delete(FilterList))
        await session.flush()

    existing_rules = set((await session.execute(select(Rule.text))).scalars().all())
    imported = skipped = 0
    for raw in state.rules:
        text = normalise(raw)
        if not text or is_comment(text):
            skipped += 1
            continue
        if text in existing_rules:
            skipped += 1
            continue
        existing_rules.add(text)
        session.add(
            Rule(
                text=text,
                kind=classify(text).value,
                origin=RuleOrigin.custom.value,
                enabled=True,
                comment=f"Imported from {instance.name}",
            )
        )
        imported += 1

    existing_lists = {
        (kind, url)
        for url, kind in (
            await session.execute(select(FilterList.url, FilterList.kind))
        ).all()
    }
    lists_imported = 0
    for item in state.filter_lists:
        if not item.url or (item.kind, item.url) in existing_lists:
            continue
        existing_lists.add((item.kind, item.url))
        session.add(
            FilterList(
                name=item.name or item.url,
                url=item.url,
                kind=item.kind,
                enabled=item.enabled,
            )
        )
        lists_imported += 1

    dns_imported = False
    if include_dns and state.dns:
        settings = await session.get(DnsSettings, 1)
        if settings is None:
            settings = DnsSettings(id=1)
            session.add(settings)
        settings.managed = True
        settings.upstream_dns = "\n".join(state.dns.get("upstream_dns") or [])
        settings.bootstrap_dns = "\n".join(state.dns.get("bootstrap_dns") or [])
        settings.fallback_dns = "\n".join(state.dns.get("fallback_dns") or [])
        settings.upstream_mode = str(state.dns.get("upstream_mode") or "")
        settings.dnssec_enabled = bool(state.dns.get("dnssec_enabled"))
        settings.protection_enabled = bool(state.dns.get("protection_enabled", True))
        dns_imported = True

    await session.commit()
    return ImportResult(
        instance=instance.name,
        rules_imported=imported,
        rules_skipped=skipped,
        filter_lists_imported=lists_imported,
        dns_imported=dns_imported,
        replaced=replace,
    )
