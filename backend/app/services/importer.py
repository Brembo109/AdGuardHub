"""Initial import from a chosen master instance (spec §7).

One instance's configuration is taken wholesale as the starting state; the others are
overwritten on the next push. There is no merge between instances, by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..adapters.sections import SECTION_NAMES, SPEC_BY_NAME
from ..models import FilterList, Instance, Rule, RuleOrigin
from ..runtime import get_crypto
from .config import set_section
from .rules import classify, is_comment, normalise


@dataclass(slots=True)
class ImportResult:
    instance: str
    rules_imported: int
    rules_skipped: int
    filter_lists_imported: int
    sections_imported: list[str]
    sections_unsupported: list[str]
    # Adopted but left switched off, because enabling them can lock a node out.
    sections_needing_review: list[str]
    replaced: bool


async def import_from_instance(
    session: AsyncSession,
    instance: Instance,
    *,
    replace: bool = True,
    sections: tuple[str, ...] = SECTION_NAMES,
) -> ImportResult:
    """Adopt the master's configuration, including every settings section it exposes.

    Imported sections are switched on, so the second node receives them on the next
    push — that is the point of naming a master. Sections marked risky are the
    exception: their values are adopted but replication stays off until the operator
    turns it on deliberately. Enabling encryption on a node that has no certificate
    would make it unreachable, and an import is not an informed decision about that.
    """
    adapter = build_adapter(instance, get_crypto())
    try:
        state = await adapter.pull_state(tuple(sections))
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

    imported_sections: list[str] = []
    unsupported: list[str] = []
    needs_review: list[str] = []
    for name in sections:
        data = state.sections.get(name)
        if data is None:
            # The instance does not implement this area; nothing to adopt.
            unsupported.append(name)
            continue
        risky = SPEC_BY_NAME[name].risky
        await set_section(session, name, data=data, managed=not risky)
        imported_sections.append(name)
        if risky:
            needs_review.append(name)

    await session.commit()
    return ImportResult(
        instance=instance.name,
        rules_imported=imported,
        rules_skipped=skipped,
        filter_lists_imported=lists_imported,
        sections_imported=imported_sections,
        sections_unsupported=unsupported,
        sections_needing_review=needs_review,
        replaced=replace,
    )
