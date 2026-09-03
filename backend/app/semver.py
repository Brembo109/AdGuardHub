"""Comparing two version strings, for the hub and for the nodes it manages.

Both questions — "is there a newer AdGuardHub" and "is there a newer AdGuard
Home on this node" — are the same comparison, and getting it wrong in either
place shows an operator an update to the version they are already running.

It lives here rather than beside either caller because an adapter must not
import from services, and a service must not import from adapters.
"""

from __future__ import annotations

import re

_RELEASE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def parse_version(text: str) -> tuple[int, ...] | None:
    """``v0.3.1`` → ``(0, 3, 1)``. Anything else — "dev", a hash — is ``None``.

    A pre-release suffix is dropped rather than ordered: ``v1.0.0-rc.1`` compares
    as ``1.0.0``, so somebody running the candidate is not told to "update" to
    the release it became. Getting that ordering right matters only if
    pre-releases are ever published, and guessing at it now would be a rule
    nobody has tested.
    """
    match = _RELEASE.match(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is a release worth telling the operator about.

    Strictly newer, not merely different. Equality is the case that made this
    matter — a node reporting the version it is running as the one available —
    but "different" would also have offered a downgrade as an update.

    An unparseable *current* is never "out of date": a development build or a
    checkout is not on the release track at all, and nagging it would be noise.
    """
    left, right = parse_version(latest), parse_version(current)
    return bool(left and right and left > right)
