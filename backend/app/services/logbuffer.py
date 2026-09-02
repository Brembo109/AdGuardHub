"""The hub's own log, kept in memory so the interface can show it.

The application log answers "what did the hub just do", and until now reading it
meant leaving the interface for `docker logs` or a shell — which is exactly what
you do not have when you are looking at a hub from a phone, or helping someone
else look at theirs.

This is a third handler beside the stream and the optional file, not a
replacement for either: the container runtime's copy stays the record, and this
is a window onto the last few hundred lines.

Three things make it safe to attach to the root logger:

**It cannot recurse.** Serving the log is itself an HTTP request, which uvicorn's
access logger logs, which lands here. That is fine — appending to a deque logs
nothing — but anything richer (publishing an event, touching the database) would
log again and feed itself. So this handler does one thing.

**It cannot grow.** A bounded deque, so a hub left running for a month holds the
same memory as one started this morning.

**It cannot leak what the log itself would not.** Formatting is the same
formatter the other handlers use, and nothing here reads the record beyond it.
The levels that would narrate bound SQL parameters are held down in
logging_setup, and that decision keeps applying because this reads the same
records.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass

#: Enough to see what a failing push or a restart did, not an archive.
MAX_LINES = 500

#: The endpoint that serves this buffer. Watching the log makes uvicorn log an
#: access line every couple of seconds, so a buffer that kept them would fill
#: with the act of being read: a few minutes of watching and the lines worth
#: seeing have scrolled out. The other handlers still record these — the
#: container log stays complete — this one just declines to eat itself.
SELF_PATH = "/api/settings/log"
ACCESS_LOGGER = "uvicorn.access"


@dataclass(frozen=True, slots=True)
class LogLine:
    #: Monotonic within a process, so the interface can ask for "what is new".
    #: Not a timestamp: two lines can share a millisecond, and a cursor that
    #: skips or repeats lines is worse than no cursor.
    seq: int
    level: str
    logger: str
    message: str
    #: ISO-8601, UTC, as the formatter renders it.
    at: str


class LogBuffer(logging.Handler):
    """The last few hundred lines, and a cursor to read forward from."""

    def __init__(self, capacity: int = MAX_LINES) -> None:
        super().__init__()
        self._lines: deque[LogLine] = deque(maxlen=capacity)
        # Records arrive from the event loop, from worker threads and from
        # uvicorn's own logger; the deque itself is thread-safe for append, but
        # the counter and the snapshot are not.
        self._lock = threading.Lock()
        self._next = 1

    def emit(self, record: logging.LogRecord) -> None:
        if _is_own_access_line(record):
            return
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 — a broken call site must not raise here
            # Deliberately not record.getMessage(): a mismatched format string —
            # logger.info("%d items", "three") — raises from exactly there, so
            # using it as the fallback re-raises the thing being handled and
            # takes down the call that was only trying to log something.
            message = f"{record.levelname} {record.name}: {record.msg!r} (unformattable)"
        at = _isoformat(record)
        # The sequence number is assigned under the lock, because it is the one
        # piece of state two threads could otherwise hand out twice.
        with self._lock:
            self._lines.append(
                LogLine(
                    seq=self._next,
                    level=record.levelname,
                    logger=record.name,
                    message=message,
                    at=at,
                )
            )
            self._next += 1

    def since(self, cursor: int = 0, limit: int = MAX_LINES) -> list[LogLine]:
        """Lines after ``cursor``, oldest first.

        A cursor from before the buffer wrapped simply gets what is left, which
        is the honest answer: those lines are gone, and pretending otherwise
        would mean holding them.
        """
        with self._lock:
            lines = [line for line in self._lines if line.seq > cursor]
        return lines[-limit:] if limit > 0 else lines

    def latest_seq(self) -> int:
        with self._lock:
            return self._next - 1

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


def _is_own_access_line(record: logging.LogRecord) -> bool:
    """Is this uvicorn reporting a request for the log itself?

    Matched on the raw arguments rather than the formatted line, because the
    format is uvicorn's to change and the arguments are the request.
    """
    if record.name != ACCESS_LOGGER:
        return False
    # The path itself or the path with a query string — not merely something
    # starting with the same letters. A bare prefix match would also swallow
    # /api/settings/logo.png, and any future route that begins this way.
    return any(
        isinstance(arg, str) and (arg == SELF_PATH or arg.startswith(f"{SELF_PATH}?"))
        for arg in record.args or ()
    )


def _isoformat(record: logging.LogRecord) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z")


_buffer: LogBuffer | None = None


def get_buffer() -> LogBuffer:
    """The process-wide buffer, created on first use."""
    global _buffer
    if _buffer is None:
        _buffer = LogBuffer()
    return _buffer
