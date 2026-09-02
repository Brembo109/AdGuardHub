"""Asking to be upgraded, from a hub that holds no privilege to do it.

The design is the point of most of these tests. The hub cannot upgrade itself and
is never given the ability to: it writes one empty file, and root-owned systemd
units do the rest. So what is worth testing is not "does it upgrade" — nothing
here does — but that the surface really is that narrow, that a request carries
nothing, and that the interface can tell a run in progress from one that ended,
from one that was never picked up at all.
"""

from __future__ import annotations

import os

import httpx
import pytest

from app.services import selfupdate

pytestmark = pytest.mark.usefixtures("fresh_db")


def write_log(data_dir, text: str, *, age: float = 0.0) -> None:
    path = selfupdate.log_path(str(data_dir))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    if age:
        when = os.path.getmtime(path) - age
        os.utime(path, (when, when))


# --------------------------------------------------------------------------
# The request carries nothing
# --------------------------------------------------------------------------


def test_the_request_is_an_empty_file(tmp_path) -> None:
    """Its existence is the whole message.

    Anything in it would be an input to a process running as root, chosen by
    whoever is talking to the web interface. There is nothing in it.
    """
    selfupdate.request(str(tmp_path))
    path = selfupdate.trigger_path(str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) == 0


def test_pressing_twice_is_still_one_request(tmp_path) -> None:
    selfupdate.request(str(tmp_path))
    selfupdate.request(str(tmp_path))
    assert os.path.getsize(selfupdate.trigger_path(str(tmp_path))) == 0


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root ignores the mode bits, so there is no unwritable directory to test with",
)
def test_a_directory_it_cannot_write_is_reported_rather_than_guessed(tmp_path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert selfupdate.available(str(locked)) is False
    finally:
        locked.chmod(0o700)


def test_a_data_dir_that_is_not_a_directory_is_not_available(tmp_path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("")
    assert selfupdate.available(str(file_path)) is False


def test_a_missing_directory_is_not_available(tmp_path) -> None:
    assert selfupdate.available(str(tmp_path / "nope")) is False


# --------------------------------------------------------------------------
# Reading a run back
# --------------------------------------------------------------------------


def test_nothing_has_happened(tmp_path) -> None:
    run = selfupdate.read_run(str(tmp_path))
    assert (run.requested, run.running, run.finished, run.stalled) == (False, False, False, False)


def test_a_fresh_request_reads_as_running(tmp_path) -> None:
    selfupdate.request(str(tmp_path))
    run = selfupdate.read_run(str(tmp_path))
    assert run.requested and run.running and not run.finished


def test_a_log_that_has_started_reads_as_running(tmp_path) -> None:
    """The updater removes the trigger before it starts, so the log is the signal."""
    write_log(tmp_path, "[start] 2026-09-01 10:00:00Z\n[fetch] …\n")
    run = selfupdate.read_run(str(tmp_path))
    assert run.running and not run.requested


def test_the_exit_marker_ends_the_run(tmp_path) -> None:
    write_log(tmp_path, "[start] …\n[done] AdGuardHub was upgraded.\n[exit 0]\n")
    run = selfupdate.read_run(str(tmp_path))
    assert run.finished and not run.running
    assert run.exit_status == 0


def test_a_failure_carries_its_status(tmp_path) -> None:
    write_log(tmp_path, "[start] …\n[failed] …\n[exit 7]\n")
    run = selfupdate.read_run(str(tmp_path))
    assert run.finished and run.exit_status == 7


def test_a_request_nothing_picks_up_is_reported_as_stalled(tmp_path) -> None:
    """A hub installed before the update units existed writes a file nobody reads.

    Without this the interface would show a spinner that never stops, which is
    the worst of the three answers: it looks like something is happening.
    """
    selfupdate.request(str(tmp_path))
    path = selfupdate.trigger_path(str(tmp_path))
    when = os.path.getmtime(path) - selfupdate.STALLED_AFTER - 5
    os.utime(path, (when, when))

    run = selfupdate.read_run(str(tmp_path))
    assert run.stalled and not run.running


def test_last_month_s_upgrade_is_not_this_afternoon_s(tmp_path) -> None:
    """The log survives the upgrade it describes; it must not be shown forever."""
    write_log(tmp_path, "[start] …\n[exit 0]\n", age=selfupdate.RECENT_SECONDS + 60)
    run = selfupdate.read_run(str(tmp_path))
    assert not run.finished and not run.running
    assert run.log == ""
    assert run.exit_status is None


def test_a_second_upgrade_is_not_read_as_the_first_one_ending(tmp_path) -> None:
    """Reported from a real hub: the button did nothing on the second press.

    The updater truncates the log when it starts, so between the press and the
    path unit firing, the only log on disk is the previous upgrade's — ending in
    its own ``[exit 0]``. Reading that as this run's outcome meant the request
    came back neither running nor finished, and the interface dropped straight
    back to an idle button while the upgrade went ahead behind it.
    """
    write_log(tmp_path, "[start] last week\n[exit 0]\n", age=selfupdate.RECENT_SECONDS + 300)
    selfupdate.request(str(tmp_path))

    run = selfupdate.read_run(str(tmp_path))
    assert run.requested and run.running
    # Last week's success is not this press's outcome, and must not be shown.
    assert not run.finished
    assert run.exit_status is None
    assert run.log == ""


def test_pressing_again_just_after_an_upgrade_does_not_report_that_one(tmp_path) -> None:
    """The same fault, with a log too recent for the age check to catch it."""
    write_log(tmp_path, "[start] a moment ago\n[exit 0]\n", age=5)
    selfupdate.request(str(tmp_path))

    run = selfupdate.read_run(str(tmp_path))
    assert run.running and not run.finished
    assert run.exit_status is None


def test_the_log_takes_over_once_the_updater_starts_writing(tmp_path) -> None:
    """The trigger is removed first, so the new log is this run's from then on."""
    write_log(tmp_path, "[start] last week\n[exit 0]\n", age=selfupdate.RECENT_SECONDS + 300)
    selfupdate.request(str(tmp_path))
    os.remove(selfupdate.trigger_path(str(tmp_path)))
    write_log(tmp_path, "[start] now\n[fetch] …\n")

    run = selfupdate.read_run(str(tmp_path))
    assert run.running and not run.finished
    assert "now" in run.log

    write_log(tmp_path, "[start] now\n[done] AdGuardHub was upgraded.\n[exit 0]\n")
    done = selfupdate.read_run(str(tmp_path))
    assert done.finished and not done.running and done.exit_status == 0


def test_only_the_tail_of_a_long_log_is_kept(tmp_path) -> None:
    """The installer is chatty; the operator is watching the end of it."""
    write_log(tmp_path, "x" * (selfupdate.MAX_LOG_BYTES * 2) + "\n[exit 0]\n")
    run = selfupdate.read_run(str(tmp_path))
    assert len(run.log) <= selfupdate.MAX_LOG_BYTES + 32
    assert run.exit_status == 0, "the end of the log is the half that matters"


# --------------------------------------------------------------------------
# Through the API
# --------------------------------------------------------------------------


async def test_starting_an_update_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/settings/update/run")).status_code == 401


async def test_reading_the_run_needs_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/settings/update/run")).status_code == 401


async def test_a_container_is_told_it_cannot_upgrade_itself(
    auth_client: httpx.AsyncClient, monkeypatch
) -> None:
    monkeypatch.setenv("ADGUARDHUB_INSTALL_METHOD", "docker")
    response = await auth_client.post("/api/settings/update/run")
    assert response.status_code == 409
    assert "cannot upgrade itself" in response.json()["detail"]


async def test_a_checkout_is_told_the_same(auth_client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("ADGUARDHUB_INSTALL_METHOD", "source")
    assert (await auth_client.post("/api/settings/update/run")).status_code == 409


async def test_a_native_install_writes_the_trigger_and_nothing_else(
    auth_client: httpx.AsyncClient, monkeypatch
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ADGUARDHUB_INSTALL_METHOD", "native")
    data_dir = get_settings().data_dir

    body = (await auth_client.post("/api/settings/update/run")).json()
    assert body["requested"] and body["running"]
    assert os.path.getsize(selfupdate.trigger_path(data_dir)) == 0

    # And the state can be read back, which is what the progress view polls.
    assert (await auth_client.get("/api/settings/update/run")).json()["requested"] is True
