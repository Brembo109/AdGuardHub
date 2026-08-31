"""Blocklist / allowlist subscription management (spec §3, §12).

AdGuardHub tracks the subscription URL and its enabled state only — resolving the
700k-domain lists behind them stays AdGuard's job.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..deps import CurrentUser, SessionDep
from ..models import FilterList, ListKind, PayloadKind
from ..schemas import FilterListCreate, FilterListOut, FilterListUpdate
from ..services.sync import schedule_sync
from ..services.versions import record as _record

router = APIRouter(prefix="/api/filter-lists", tags=["filter-lists"])

LIST_KINDS = (PayloadKind.filters,)


@router.get("", response_model=list[FilterListOut])
async def list_filter_lists(
    user: CurrentUser, session: SessionDep, kind: ListKind | None = None
) -> list[FilterList]:
    statement = select(FilterList).order_by(FilterList.id.asc())
    if kind is not None:
        statement = statement.where(FilterList.kind == kind.value)
    result = await session.execute(statement)
    return list(result.scalars().all())


@router.post("", response_model=FilterListOut, status_code=status.HTTP_201_CREATED)
async def create_filter_list(
    payload: FilterListCreate, user: CurrentUser, session: SessionDep
) -> FilterList:
    item = FilterList(
        name=payload.name, url=payload.url, kind=payload.kind.value, enabled=payload.enabled
    )
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That subscription already exists") from exc
    await record_version(session, f"subscription added: {item.url}", user)
    schedule_sync(LIST_KINDS, f"subscription added: {item.url}")
    return item


@router.patch("/{list_id}", response_model=FilterListOut)
async def update_filter_list(
    list_id: int, payload: FilterListUpdate, user: CurrentUser, session: SessionDep
) -> FilterList:
    item = await session.get(FilterList, list_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    await session.commit()
    await record_version(session, f"subscription updated: {item.url}", user)
    schedule_sync(LIST_KINDS, f"subscription updated: {item.url}")
    return item


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_filter_list(list_id: int, user: CurrentUser, session: SessionDep) -> None:
    item = await session.get(FilterList, list_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    url = item.url
    await session.delete(item)
    await session.commit()
    await record_version(session, f"subscription removed: {url}", user)
    schedule_sync(LIST_KINDS, f"subscription removed: {url}")


async def record_version(session: SessionDep, label: str, user: CurrentUser) -> None:
    """Snapshot the central state so the change can be diffed and rolled back."""
    await _record(session, label, author=user.username)
