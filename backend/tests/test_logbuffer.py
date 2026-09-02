"""The hub's own log, readable from the interface.

The application log answers "what did the hub just do", and reading it used to
mean leaving the interface for a shell — which is what you do not have when you
are looking at a hub from a phone.

The risks are all in the handler rather than the view. A handler on the root
logger sees every line the hub produces, including the ones produced by serving
this very endpoint, so it must not do anything that logs; it must not grow; and
it must not become a second route by which something reaches the log that the
log itself would not carry.
"""

from __future__ import annotations

import logging

import httpx

from app.services.logbuffer import MAX_LINES, LogBuffer


def buffer_with(*messages: str, level: int = logging.INFO) -> LogBuffer:
    buffer = LogBuffer()
    buffer.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    for message in messages:
        buffer.emit(
            logging.LogRecord("adguardhub", level, __file__, 1, message, None, None)
        )
    return buffer


# --------------------------------------------------------------------------
# The handler
# --------------------------------------------------------------------------


def test_lines_come_back_oldest_first() -> None:
    buffer = buffer_with("first", "second", "third")
    assert [line.message.split(": ")[-1] for line in buffer.since(0)] == [
        "first",
        "second",
        "third",
    ]


def test_the_cursor_returns_only_what_is_new() -> None:
    """Following along must cost one small response, not the whole buffer."""
    buffer = buffer_with("a", "b")
    cursor = buffer.latest_seq()
    buffer.emit(logging.LogRecord("adguardhub", logging.INFO, __file__, 1, "c", None, None))

    fresh = buffer.since(cursor)
    assert [line.message.split(": ")[-1] for line in fresh] == ["c"]


def test_a_cursor_at_the_end_returns_nothing() -> None:
    buffer = buffer_with("a", "b")
    assert buffer.since(buffer.latest_seq()) == []


def test_the_buffer_does_not_grow_without_limit() -> None:
    """A hub left running for a month holds what one started this morning does."""
    buffer = buffer_with(*[f"line {index}" for index in range(MAX_LINES + 250)])
    assert len(buffer.since(0)) == MAX_LINES


def test_sequence_numbers_survive_the_buffer_wrapping() -> None:
    """They number lines, not slots: a cursor must never go backwards."""
    buffer = buffer_with(*[f"line {index}" for index in range(MAX_LINES + 10)])
    lines = buffer.since(0)
    assert lines[0].seq < lines[-1].seq
    assert buffer.latest_seq() == MAX_LINES + 10
    assert [line.seq for line in lines] == sorted(line.seq for line in lines)


def test_a_cursor_from_before_the_wrap_gets_what_is_left() -> None:
    buffer = buffer_with(*[f"line {index}" for index in range(MAX_LINES + 50)])
    # Line 1 is long gone; asking for it must not raise or return everything twice.
    assert len(buffer.since(1)) == MAX_LINES


def test_a_broken_format_string_does_not_raise_out_of_the_handler() -> None:
    """A handler that raises breaks whatever was being logged, not just itself."""
    buffer = LogBuffer()
    buffer.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        "adguardhub", logging.INFO, __file__, 1, "%d items", ("not a number",), None
    )
    buffer.emit(record)
    assert len(buffer.since(0)) == 1


def test_the_level_is_carried_so_a_reader_can_pick_out_failures() -> None:
    buffer = buffer_with("something went wrong", level=logging.WARNING)
    assert buffer.since(0)[0].level == "WARNING"


def access_record(path: str, logger: str = "uvicorn.access") -> logging.LogRecord:
    """One uvicorn access line, in the shape uvicorn actually produces it."""
    return logging.LogRecord(
        logger,
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", path, "1.1", 200),
        None,
    )


def test_watching_the_log_does_not_fill_the_log() -> None:
    """The viewer polls every couple of seconds, and uvicorn logs each poll.

    Kept, those lines would push everything worth reading out of a 500-line
    buffer within minutes — the act of watching would destroy what you came to
    watch. The other handlers still record them; only this one declines.
    """
    buffer = LogBuffer()
    buffer.setFormatter(logging.Formatter("%(message)s"))
    buffer.emit(access_record("/api/settings/log"))
    buffer.emit(access_record("/api/settings/log?cursor=42"))
    assert buffer.since(0) == []


def test_every_other_request_is_still_recorded() -> None:
    """Narrowly scoped: this is not "hide the access log"."""
    buffer = LogBuffer()
    buffer.setFormatter(logging.Formatter("%(message)s"))
    buffer.emit(access_record("/api/dashboard"))
    buffer.emit(access_record("/control/status"))
    buffer.emit(access_record("/api/settings/logo.png"))

    paths = [line.message for line in buffer.since(0)]
    assert len(paths) == 3, "a request that merely looks similar was dropped"


def test_another_logger_saying_the_same_path_is_kept() -> None:
    """Matched on uvicorn's access logger, not on the text of any line."""
    buffer = LogBuffer()
    buffer.setFormatter(logging.Formatter("%(message)s"))
    buffer.emit(access_record("/api/settings/log", logger="adguardhub"))
    assert len(buffer.since(0)) == 1


# --------------------------------------------------------------------------
# Attached to the hub
# --------------------------------------------------------------------------


def test_the_hub_installs_it_alongside_the_other_handlers() -> None:
    from app.logging_setup import configure
    from app.services.logbuffer import get_buffer

    configure("INFO")
    assert get_buffer() in logging.getLogger().handlers
    # The stream handler is still there: this is a window, not a replacement.
    assert any(
        isinstance(handler, logging.StreamHandler) and handler is not get_buffer()
        for handler in logging.getLogger().handlers
    )


# --------------------------------------------------------------------------
# Through the API
# --------------------------------------------------------------------------


async def test_the_log_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/settings/log")).status_code == 401


async def test_the_endpoint_returns_lines_and_a_cursor(auth_client: httpx.AsyncClient) -> None:
    logging.getLogger("adguardhub").warning("a line for the test to find")

    body = (await auth_client.get("/api/settings/log")).json()
    assert body["lines"], "the buffer answered empty while the hub was logging"
    assert any("a line for the test to find" in line["message"] for line in body["lines"])
    assert body["cursor"] == body["lines"][-1]["seq"]


async def test_following_along_returns_only_new_lines(auth_client: httpx.AsyncClient) -> None:
    first = (await auth_client.get("/api/settings/log")).json()
    logging.getLogger("adguardhub").info("something after the cursor")

    second = (await auth_client.get(f"/api/settings/log?cursor={first['cursor']}")).json()
    assert second["lines"], "the second poll saw nothing new"
    seqs = [line["seq"] for line in second["lines"]]
    assert min(seqs) > first["cursor"]


async def test_the_limit_cannot_be_used_to_ask_for_everything(
    auth_client: httpx.AsyncClient,
) -> None:
    """`limit` is clamped, so one request cannot be turned into a large one."""
    body = (await auth_client.get("/api/settings/log?limit=100000")).json()
    assert len(body["lines"]) <= MAX_LINES
