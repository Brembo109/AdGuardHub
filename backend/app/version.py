"""The release this build was cut from.

Its own module so that anything can ask — the health endpoint, the update check —
without importing the application, which imports everything else.
"""

from __future__ import annotations

import os


def build_version() -> str:
    """The tag this build came from, or ``dev``.

    The Release workflow passes the git tag into the image build, which bakes it
    in as ADGUARDHUB_VERSION; the native installer writes it into the systemd
    unit. Nothing in the source tree carries a number, so a version here can
    never drift out of step with the tags the way a hand-edited constant does —
    and a build that came from no tag says so rather than claiming to be the last
    release someone happened to write down.
    """
    return os.environ.get("ADGUARDHUB_VERSION", "").strip() or "dev"


VERSION = build_version()
