"""Startup check for the data directory.

A bind-mounted /data keeps the host directory's ownership, so the container's app
user may not be able to write there. That must fail with a message naming the fix,
not with a bare "unable to open database file".
"""

from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.db import DataDirError, check_data_dir


def test_writable_directory_passes(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_DATA_DIR", str(tmp_path / "data"))
    check_data_dir()
    assert (tmp_path / "data").is_dir()
    # The probe file must not be left behind.
    assert list((tmp_path / "data").iterdir()) == []
    get_settings.cache_clear()


@pytest.mark.skipif(os.getuid() == 0, reason="root ignores directory permissions")
def test_unwritable_directory_explains_the_fix(tmp_path, monkeypatch) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)

    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_DATA_DIR", str(locked))
    try:
        with pytest.raises(DataDirError) as caught:
            check_data_dir()
    finally:
        locked.chmod(0o755)
        get_settings.cache_clear()

    message = str(caught.value)
    assert "not writable" in message
    assert "PUID" in message and "PGID" in message
    assert str(locked) in message


@pytest.mark.skipif(os.getuid() == 0, reason="root ignores file permissions")
def test_unwritable_existing_database_is_reported(tmp_path, monkeypatch) -> None:
    """A writable directory still fails if an earlier run left a root-owned DB."""
    data = tmp_path / "data"
    data.mkdir()
    database = data / "adguardhub.db"
    database.write_bytes(b"")
    database.chmod(0o444)

    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_DATA_DIR", str(data))
    try:
        with pytest.raises(DataDirError) as caught:
            check_data_dir()
    finally:
        database.chmod(0o644)
        get_settings.cache_clear()

    assert "not writable" in str(caught.value)
    assert "earlier run" in str(caught.value)
