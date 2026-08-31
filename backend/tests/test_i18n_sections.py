"""Section metadata is translated in the frontend, but written here.

Every label, help text and group heading in ``sections.py`` is rendered through
the frontend's ``t()``, which cannot see them: they arrive over the API at
runtime, so no source scan finds them. ``frontend/src/i18n/dynamic-keys.json``
lists them for the frontend's completeness check instead, and this test is what
keeps that list from drifting the moment a field is added or reworded here.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.sections import SPECS

KEY_FILE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "dynamic-keys.json"


def ui_strings() -> set[str]:
    """Everything from a section spec that a person actually reads."""
    strings: set[str] = set()
    for section in SPECS:
        strings.update(x for x in (section.title, section.description, section.notes) if x)
        for spec in section.fields:
            strings.update(x for x in (spec.label, spec.help, spec.unit, spec.group) if x)
            strings.update(label for _value, label in spec.options)
    return strings


def test_every_section_string_is_listed_for_translation() -> None:
    listed = set(json.loads(KEY_FILE.read_text(encoding="utf-8")))
    missing = sorted(ui_strings() - listed)
    assert not missing, (
        f"Add these to {KEY_FILE.name} (and a German entry to de.ts) — "
        f"they are shown in the UI but nothing would translate them: {missing}"
    )
