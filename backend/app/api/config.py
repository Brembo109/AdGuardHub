"""Managed configuration sections and the version history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..adapters.sections import SPECS, SectionSpec
from ..deps import CurrentUser, SessionDep
from ..models import PayloadKind
from ..schemas import (
    ConfigFieldOut,
    ConfigSectionOut,
    ConfigSectionUpdate,
    VersionDetail,
    VersionDiff,
    VersionOut,
    VersionRestoreResult,
)
from ..services import versions as version_service
from ..services.config import get_section, loads, set_section, skipped_sections
from ..services.sync import schedule_sync

router = APIRouter(prefix="/api/config", tags=["config"])


def _fields(spec: SectionSpec) -> list[ConfigFieldOut]:
    return [
        ConfigFieldOut(
            key=field.key,
            label=field.label,
            type=field.type,
            help=field.help,
            unit=field.unit,
            options=[list(option) for option in field.options],
        )
        for field in spec.fields
    ]

SETTING_KINDS = (PayloadKind.settings,)


@router.get("/sections", response_model=list[ConfigSectionOut])
async def list_sections(_: CurrentUser, session: SessionDep) -> list[ConfigSectionOut]:
    skipped = await skipped_sections(session)
    out: list[ConfigSectionOut] = []
    for spec in SPECS:
        row = await get_section(session, spec.name)
        data = loads(row.data)
        out.append(
            ConfigSectionOut(
                name=spec.name,
                title=spec.title,
                description=spec.description,
                notes=spec.notes,
                risky=spec.risky,
                fields=_fields(spec),
                managed=row.managed,
                has_data=bool(data),
                keys=sorted(data),
                data=data,
                skipped_reason=skipped.get(spec.name, ""),
                updated_at=row.updated_at,
            )
        )
    return out


@router.patch("/sections/{name}", response_model=ConfigSectionOut)
async def update_section(
    name: str, payload: ConfigSectionUpdate, user: CurrentUser, session: SessionDep
) -> ConfigSectionOut:
    try:
        row = await set_section(session, name, managed=payload.managed, data=payload.data)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown section {name!r}") from exc

    await version_service.record(
        session, f"section '{name}' updated", author=user.username, kind="change"
    )
    if row.managed:
        schedule_sync(SETTING_KINDS, f"section '{name}' updated")

    data = loads(row.data)
    spec = next(item for item in SPECS if item.name == name)
    skipped = await skipped_sections(session)
    return ConfigSectionOut(
        name=spec.name,
        title=spec.title,
        description=spec.description,
        notes=spec.notes,
        risky=spec.risky,
        fields=_fields(spec),
        managed=row.managed,
        has_data=bool(data),
        keys=sorted(data),
        data=data,
        skipped_reason=skipped.get(name, ""),
        updated_at=row.updated_at,
    )


# -- versions --------------------------------------------------------------

versions_router = APIRouter(prefix="/api/versions", tags=["versions"])


@versions_router.get("", response_model=list[VersionOut])
async def list_versions(
    _: CurrentUser, session: SessionDep, limit: int = Query(50, ge=1, le=200)
) -> list[VersionOut]:
    from sqlalchemy import select

    from ..models import ConfigVersion

    result = await session.execute(
        select(ConfigVersion).order_by(ConfigVersion.id.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    out: list[VersionOut] = []
    for index, row in enumerate(rows):
        previous = rows[index + 1] if index + 1 < len(rows) else None
        summary = "initial snapshot"
        if previous is not None:
            summary = version_service.summarise(
                version_service.diff(version_service.decode(previous), version_service.decode(row))
            )
        out.append(
            VersionOut(
                id=row.id,
                label=row.label,
                author=row.author,
                kind=row.kind,
                summary=summary,
                created_at=row.created_at,
            )
        )
    return out


@versions_router.get("/{version_id}", response_model=VersionDetail)
async def get_version(version_id: int, _: CurrentUser, session: SessionDep) -> VersionDetail:
    version = await version_service.get(session, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    return VersionDetail(
        id=version.id,
        label=version.label,
        author=version.author,
        kind=version.kind,
        created_at=version.created_at,
        snapshot=version_service.decode(version),
    )


@versions_router.get("/{version_id}/diff", response_model=VersionDiff)
async def diff_version(
    version_id: int,
    _: CurrentUser,
    session: SessionDep,
    against: int | None = Query(None, description="Version to compare with; default is current"),
) -> VersionDiff:
    version = await version_service.get(session, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    if against is None:
        from ..services.config import build_snapshot

        other_snapshot = await build_snapshot(session)
        other_label = "current state"
        other_id = None
    else:
        other = await version_service.get(session, against)
        if other is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparison version not found")
        other_snapshot = version_service.decode(other)
        other_label = f"version {other.id}"
        other_id = other.id

    changes = version_service.diff(version_service.decode(version), other_snapshot)
    return VersionDiff(
        from_id=version.id,
        to_id=other_id,
        to_label=other_label,
        summary=version_service.summarise(changes),
        changes=changes,
    )


@versions_router.post("/{version_id}/restore", response_model=VersionRestoreResult)
async def restore_version(
    version_id: int, user: CurrentUser, session: SessionDep, push: bool = True
) -> VersionRestoreResult:
    """Roll the central state back, then push it out like any other change."""
    version = await version_service.get(session, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")

    counts = await version_service.restore(session, version, author=user.username)
    if push:
        from ..services.sync import ALL_KINDS

        schedule_sync(ALL_KINDS, f"rollback to version {version.id}")
    return VersionRestoreResult(
        version_id=version.id,
        rules=counts["rules"],
        filter_lists=counts["filter_lists"],
        sections=counts["sections"],
        pushed=push,
    )
