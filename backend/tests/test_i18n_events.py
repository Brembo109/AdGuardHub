"""Notification events are declared here, but labelled in the frontend.

``KNOWN_EVENTS`` drives the checkboxes under Settings, and the label for each one
lives in ``Settings.tsx`` as ``EVENT_LABELS``. That map is read as
``t(EVENT_LABELS[name] ?? name)``, so an event nobody labelled does not fail —
it renders its own id, and ``instance.recovered`` appears in the interface as a
checkbox called "instance.recovered".

Nothing else would catch it: the frontend's own i18n check walks ``t()`` call
sites, and this label reaches ``t()`` through a variable. So the check has to be
here, next to the list that the labels are supposed to track.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.notify import KNOWN_EVENTS

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PAGE = ROOT / "frontend" / "src" / "pages" / "Settings.tsx"
KEY_FILE = ROOT / "frontend" / "src" / "i18n" / "dynamic-keys.json"

# The EVENT_LABELS object literal, up to its closing brace.
LABEL_BLOCK = re.compile(r"const EVENT_LABELS[^{]*\{(.*?)\n\}", re.DOTALL)
ENTRY = re.compile(r"'([^']+)':\s*'([^']*)'")


def labels() -> dict[str, str]:
    block = LABEL_BLOCK.search(SETTINGS_PAGE.read_text(encoding="utf-8"))
    assert block, f"EVENT_LABELS not found in {SETTINGS_PAGE.name} — did it move or get renamed?"
    return dict(ENTRY.findall(block.group(1)))


def test_every_event_has_a_label() -> None:
    missing = sorted(set(KNOWN_EVENTS) - set(labels()))
    assert not missing, (
        f"Add these to EVENT_LABELS in {SETTINGS_PAGE.name} — without a label the "
        f"UI shows the bare event id as a checkbox: {missing}"
    )


def test_no_label_outlives_its_event() -> None:
    """A label for an event that no longer exists is a checkbox that does nothing."""
    extra = sorted(set(labels()) - set(KNOWN_EVENTS))
    assert not extra, (
        f"Remove these from EVENT_LABELS in {SETTINGS_PAGE.name} — no such event "
        f"is emitted any more: {extra}"
    )


def test_every_label_is_listed_for_translation() -> None:
    listed = set(json.loads(KEY_FILE.read_text(encoding="utf-8")))
    missing = sorted(set(labels().values()) - listed)
    assert not missing, (
        f"Add these to {KEY_FILE.name} (and a German entry to de.ts) — they are "
        f"shown in the UI but nothing would translate them: {missing}"
    )
