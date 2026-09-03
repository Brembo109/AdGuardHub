"""Download one file that answers the first ten questions of a bug report."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..deps import CurrentUser, SessionDep
from ..services import diagnostics

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
async def download(_: CurrentUser, session: SessionDep) -> JSONResponse:
    """The redacted diagnostic bundle, as an attachment.

    Behind the session cookie like everything else: it is less revealing than a
    backup, but "less revealing" is not "public", and it carries the rule set
    and the recent log.
    """
    document = await diagnostics.build(session)
    stamp = str(document["created_at"])[:10]
    return JSONResponse(
        content=document,
        headers={
            "Content-Disposition": f'attachment; filename="adguardhub-diagnostics-{stamp}.json"'
        },
    )
