"""Every replicated key should be reachable from a form, or deliberately not.

A key listed in ``SectionSpec.keys`` is read from the node, stored, replicated
and rolled back. A key with no ``FieldSpec`` is all of that *and* invisible: it
only appears behind "Edit raw document", where nobody looks for a timeout.

That is a legitimate choice for a few keys, and an oversight for the rest — and
nothing distinguished the two, which is how the upstream timeout and the rate
limit's block size ended up replicated but unexplained. The exemptions below
turn each omission into a decision somebody wrote down.
"""

from __future__ import annotations

from app.adapters.sections import SPECS

#: Keys deliberately left to the raw document, with the reason.
NO_FIELD_NEEDED = {
    # A path on the node's own filesystem. Offering a text box for it invites
    # someone to point two nodes at a file only one of them has.
    ("dns", "upstream_dns_file"),
    # A weekly schedule object. A form for it is a week planner, not a field,
    # and the hub has no opinion worth expressing about one.
    ("blocked_services", "schedule"),
    # Retention, whose unit changed between AdGuard versions — days in older
    # builds, milliseconds in current ones. A labelled field would be wrong on
    # one of them, and wrong about a retention period is worse than absent.
    ("querylog_config", "interval"),
    ("stats_config", "interval"),
}


def test_every_replicated_key_has_a_field_or_a_reason() -> None:
    uncovered = []
    for section in SPECS:
        has_field = {spec.key for spec in section.fields}
        for key in section.keys:
            if key not in has_field and (section.name, key) not in NO_FIELD_NEEDED:
                uncovered.append(f"{section.name}.{key}")

    assert not uncovered, (
        "These keys are replicated but have no field, so they are only reachable "
        "through the raw document. Add a FieldSpec, or list them in "
        f"NO_FIELD_NEEDED with the reason: {sorted(uncovered)}"
    )


def test_no_field_describes_a_key_that_is_not_replicated() -> None:
    """A field for a key outside ``keys`` edits something the push never sends."""
    stray = []
    for section in SPECS:
        if not section.keys:
            # Empty keys means the whole document is replicated, so any field is
            # covered by definition.
            continue
        for spec in section.fields:
            if spec.key not in section.keys:
                stray.append(f"{section.name}.{spec.key}")

    assert not stray, (
        "These fields are shown and edited but their key is not in the section's "
        f"keys, so the value is never pushed: {sorted(stray)}"
    )
