"""Asking to be upgraded, from a hub that holds no privilege to do it.

The hub runs as an unprivileged user under ``ProtectSystem=strict``. It cannot
write to ``/opt``, cannot restart itself, and has no sudo rule — deliberately, and
an update button is not a good enough reason to give a web application root on
the machine it is installed on.

So it does not get one. It creates a single empty file in the one directory it
can write. A systemd path unit notices, and a root oneshot unit does the
privileged half. Everything this module can do is create that file and read a log
back; there is nothing here that runs an upgrade, and nothing the hub writes
reaches the thing that does — the trigger carries no version, no URL, no
arguments at all.

Which means the worst an attacker with the admin password can do through this is
cause the hub to install the newest official release, over https, from the same
place the operator installed it from.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TRIGGER_NAME = ".update-requested"
LOG_NAME = "update.log"

# The updater's last line. Its presence is how the hub knows the run has ended
# rather than stalled, which it cannot ask systemd about from where it sits.
EXIT_MARKER = re.compile(r"^\[exit (\d+)\]$", re.MULTILINE)

# The log is progress, not an archive: the tail is what the operator is watching.
MAX_LOG_BYTES = 64 * 1024


# How long a request may sit with nothing happening before the hub stops calling
# it "running". The usual cause is a hub installed before the update units
# existed, or a path unit that was never enabled: the file is written, nothing
# watches it, and a spinner would turn forever.
STALLED_AFTER = 120.0

# How long a finished run stays worth showing. The upgrade restarts the hub, so
# the browser reloads into a fresh page and has to be able to find out how the
# run it started actually ended.
RECENT_SECONDS = 900.0


@dataclass(frozen=True)
class UpdateRun:
    """What the privileged half is doing, as far as the hub can see."""

    requested: bool
    running: bool
    finished: bool
    stalled: bool
    exit_status: int | None
    #: Seconds since the log was last written, or ``None`` when there is no log.
    age: float | None
    log: str


def trigger_path(data_dir: str) -> str:
    return os.path.join(data_dir, TRIGGER_NAME)


def log_path(data_dir: str) -> str:
    return os.path.join(data_dir, LOG_NAME)


def available(data_dir: str) -> bool:
    """Whether asking for an upgrade could work at all.

    Being able to write the trigger is necessary but not sufficient — the path
    unit has to be installed and enabled, which the hub cannot see from inside
    its own sandbox. So this is deliberately the weaker claim, and the interface
    words it as "ask", not "will".
    """
    return os.path.isdir(data_dir) and os.access(data_dir, os.W_OK)


def request(data_dir: str) -> None:
    """Create the trigger file. That is the entire privileged surface.

    Empty on purpose: there is nothing in it for a caller to steer the upgrade
    with, so the request can only ever mean "install the newest release".
    """
    path = trigger_path(data_dir)
    # Truncating an existing one is not an extra request: the path unit fires on
    # the file existing, so a second press while one is pending changes nothing.
    with open(path, "w", encoding="utf-8"):
        pass
    logger.info("An upgrade was requested from the interface")


def read_run(data_dir: str) -> UpdateRun:
    """Where the upgrade has got to, read from the file the updater writes.

    The hub may be restarted by the upgrade halfway through this — that is what
    an upgrade is — so the state has to be reconstructible from the log alone
    rather than held in memory.
    """
    now = time.time()
    trigger = trigger_path(data_dir)
    requested = os.path.exists(trigger)

    log = ""
    age: float | None = None
    path = log_path(data_dir)
    try:
        size = os.path.getsize(path)
        age = now - os.path.getmtime(path)
        with open(path, encoding="utf-8", errors="replace") as handle:
            if size > MAX_LOG_BYTES:
                handle.seek(size - MAX_LOG_BYTES)
                # The seek lands mid-line; drop the fragment rather than show it.
                handle.readline()
            log = handle.read()
    except OSError:
        # No log yet, or no upgrade has run since this hub was installed.
        pass

    match = EXIT_MARKER.search(log)
    finished = match is not None

    # A log from a previous upgrade is history, not a run in progress.
    stale = age is not None and age > RECENT_SECONDS
    started = bool(log) and not stale

    waiting = 0.0
    if requested:
        try:
            waiting = now - os.path.getmtime(trigger)
        except OSError:
            waiting = 0.0

    stalled = requested and not started and waiting > STALLED_AFTER

    return UpdateRun(
        requested=requested,
        running=(requested or started) and not finished and not stalled,
        finished=finished and not stale,
        stalled=stalled,
        exit_status=int(match.group(1)) if match and not stale else None,
        age=age,
        log="" if stale else log,
    )
