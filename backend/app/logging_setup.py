"""How the hub logs, and why it is quiet about some things and not others.

The default was INFO on everything, which made `docker logs` almost useless: a
hub polling two nodes every five seconds spends nearly all of it on httpx
reporting each request. Counted on a real run, 446 of 519 lines were httpx and
two were the hub's own.

So the level is configurable, httpx is held at WARNING unless someone is
deliberately debugging, and there is an optional file for deployments that would
rather keep their own copy than rely on the container runtime's.

Everything ends up in one stream: uvicorn's own loggers are handed to the root
so the access log shares the hub's format and reaches the file too. The one
thing deliberately left out at every level is the database layer's statement
narration — see ALWAYS_QUIET.

A third handler keeps the last few hundred lines in memory so the interface can
show them without an operator having to reach a shell. It reads the same records
as the other two, so every decision here about what is logged and what is held
quiet applies to it unchanged — see services/logbuffer.py.
"""

from __future__ import annotations

import logging
import logging.handlers
import os

from .services.logbuffer import get_buffer

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Libraries that describe their own work in detail. Useful when chasing a
# failing node, noise the rest of the time — so they follow the hub's level only
# once it is turned down to DEBUG.
CHATTY_LIBRARIES = ("httpx", "httpcore")

# Uvicorn installs its own handlers on these and stops them propagating, so
# without this its lines — the access log among them — keep a different format
# and never reach the log file. Handing them to the root makes one stream.
SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Held down even at DEBUG. aiosqlite narrates every statement *with its bound
# parameters*, which is both a wall of text and a way for a password typed into
# the username box to end up written to a log file. Nothing the hub's own debug
# output does not cover.
ALWAYS_QUIET = ("aiosqlite",)


def configure(
    level: str = "INFO",
    *,
    log_file: str = "",
    max_bytes: int = 5 * 1024 * 1024,
    backups: int = 3,
) -> None:
    """Install the hub's handlers. Safe to call more than once."""
    resolved = logging.getLevelName(str(level).strip().upper() or "INFO")
    if not isinstance(resolved, int):
        # An unreadable level must not leave the hub silent, and the complaint
        # has to go somewhere the operator will see it.
        resolved = logging.INFO
        bad_level = str(level)
    else:
        bad_level = ""

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(FORMAT)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    # Attached to the root like the others, so it sees whatever they see and
    # nothing they do not.
    buffer = get_buffer()
    buffer.setFormatter(formatter)
    root.addHandler(buffer)

    root.setLevel(resolved)

    file_error = ""
    if log_file:
        try:
            directory = os.path.dirname(log_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            rotating = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
            )
            rotating.setFormatter(formatter)
            root.addHandler(rotating)
        except OSError as exc:
            # A log file that cannot be opened is not a reason to refuse to run;
            # stderr still has everything.
            file_error = f"Cannot write the log file {log_file}: {exc}"

    for name in CHATTY_LIBRARIES:
        logging.getLogger(name).setLevel(
            logging.DEBUG if resolved <= logging.DEBUG else logging.WARNING
        )
    for name in ALWAYS_QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    for name in SERVER_LOGGERS:
        server = logging.getLogger(name)
        for handler in list(server.handlers):
            server.removeHandler(handler)
        server.propagate = True

    logger = logging.getLogger("adguardhub")
    if bad_level:
        logger.warning("Unknown ADGUARDHUB_LOG_LEVEL %r — using INFO", bad_level)
    if file_error:
        logger.warning("%s", file_error)
