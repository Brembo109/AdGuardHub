"""Is there a newer AdGuardHub than the one running, and can this install take it?

Two questions, deliberately kept apart.

**Is there a newer one** is answered by asking GitHub for the latest release. That
is one outbound request to one host, made at most once every few hours, sending
nothing but the request itself — no identifier, no version, no telemetry. It can
be switched off entirely, and a hub on a network with no internet simply reports
that it could not look, rather than growing an error banner it can do nothing
about.

**Can this install take it** depends on how the hub was installed, which it can
work out for itself. A container cannot replace its own image — that is the host's
job, and the honest answer is a `docker pull` line rather than a button that
cannot work. A native install can, because the installer is idempotent and
re-running it upgrades in place.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)

REPO = "fgrfn/adguardhub"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"

# Long enough that a hub left open all day makes a handful of requests, short
# enough that "check now" is rarely the only way to see a release from this
# morning.
CACHE_SECONDS = 6 * 3600

# A check is a convenience. It must never be the reason a page is slow, so it
# gets less time than a call to an instance does.
TIMEOUT = 8.0

# Refused answers are cached too, and for much less: a hub that comes up before
# its network does should recover in minutes, not in six hours.
FAILURE_CACHE_SECONDS = 300


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    latest: str
    update_available: bool
    release_url: str
    published_at: str
    install_method: str
    self_update: bool
    checked_at: float
    error: str


def parse_version(text: str) -> tuple[int, ...] | None:
    """``v0.3.1`` → ``(0, 3, 1)``. Anything else — "dev", a hash — is ``None``.

    A pre-release suffix is dropped rather than ordered: ``v1.0.0-rc.1`` compares
    as ``1.0.0``, so an operator running the candidate is not told to "update" to
    the release it became. Getting that ordering right matters only if
    pre-releases are ever published, and guessing at it now would be a rule
    nobody has tested.
    """
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is a release worth telling the operator about.

    An unparseable *current* — a development build, someone running from a
    checkout — is never "out of date": it is not on the release track at all, and
    nagging it would be noise.
    """
    left, right = parse_version(latest), parse_version(current)
    return bool(left and right and left > right)


def install_method() -> str:
    """``docker``, ``native`` or ``source``, worked out from the surroundings.

    The installer sets ADGUARDHUB_INSTALL_METHOD in the systemd unit, so a native
    install says so directly. Docker is detected rather than declared, because an
    image built from this repository by somebody else still runs in a container
    and still cannot update itself.
    """
    declared = os.environ.get("ADGUARDHUB_INSTALL_METHOD", "").strip().lower()
    if declared in {"docker", "native", "source"}:
        return declared
    if os.path.exists("/.dockerenv") or os.environ.get("ADGUARDHUB_DOCKER"):
        return "docker"
    return "source"


class UpdateChecker:
    """One cached answer, shared by every request that asks for it."""

    def __init__(self, current_version: str) -> None:
        self._current = current_version
        self._cached: UpdateStatus | None = None
        # Without this, opening the dashboard in three tabs makes three requests
        # to GitHub at once and two of them are thrown away.
        self._lock = asyncio.Lock()

    def _fresh(self, status: UpdateStatus, now: float) -> bool:
        age = now - status.checked_at
        return age < (FAILURE_CACHE_SECONDS if status.error else CACHE_SECONDS)

    def _blank(self, error: str, now: float) -> UpdateStatus:
        method = install_method()
        return UpdateStatus(
            current=self._current,
            latest="",
            update_available=False,
            release_url=f"https://github.com/{REPO}/releases",
            published_at="",
            install_method=method,
            self_update=False,
            checked_at=now,
            error=error,
        )

    async def get(self, *, enabled: bool, force: bool = False) -> UpdateStatus:
        now = time.time()
        if not enabled:
            # Not an error, and not a stale cached answer either: the operator
            # turned it off, so the hub has nothing to say about updates.
            return self._blank("", now)

        async with self._lock:
            cached = self._cached
            if cached is not None and not force and self._fresh(cached, now):
                return cached
            status = await self._fetch(now)
            self._cached = status
            return status

    async def _fetch(self, now: float) -> UpdateStatus:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(
                    RELEASES_URL,
                    headers={
                        "Accept": "application/vnd.github+json",
                        # GitHub asks for one and refuses anonymous requests
                        # without it. No version, no host, nothing identifying.
                        "User-Agent": "AdGuardHub",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as caught:
            status_code = caught.response.status_code
            if status_code == 404:
                # Nothing has been released yet. Not a fault to report.
                return self._blank("", now)
            logger.debug("Update check refused: HTTP %s", status_code)
            return self._blank(f"GitHub answered {status_code}", now)
        except Exception as caught:  # noqa: BLE001 — a check must never take the page down
            logger.debug("Update check failed: %s", caught)
            return self._blank("could not reach github.com", now)

        latest = str(payload.get("tag_name") or "").strip()
        if not latest:
            return self._blank("", now)

        method = install_method()
        return UpdateStatus(
            current=self._current,
            latest=latest,
            update_available=is_newer(latest, self._current),
            release_url=str(payload.get("html_url") or f"https://github.com/{REPO}/releases"),
            published_at=str(payload.get("published_at") or ""),
            install_method=method,
            # Reported, not acted on: nothing in this module updates anything.
            self_update=method == "native",
            checked_at=now,
            error="",
        )


def as_dict(status: UpdateStatus) -> dict[str, object]:
    return asdict(status)
