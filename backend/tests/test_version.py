"""The reported version comes from the release tag, or admits it does not.

The whole point of baking the tag into the image is that a running container can
be identified. If this coupling is ever severed — a constant put back, the build
arg dropped from the Dockerfile — every container would report the same number
forever and nobody would notice until they were debugging the wrong build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.main import build_version

ROOT = Path(__file__).resolve().parents[2]


def test_reports_the_tag_the_image_was_built_from(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADGUARDHUB_VERSION", "0.2.0")
    assert build_version() == "0.2.0"


def test_a_build_from_no_tag_says_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADGUARDHUB_VERSION", raising=False)
    assert build_version() == "dev"


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_an_empty_build_arg_is_not_a_version(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset --build-arg arrives as an empty string, not as an absent variable."""
    monkeypatch.setenv("ADGUARDHUB_VERSION", value)
    assert build_version() == "dev"


def test_the_dockerfile_still_passes_the_build_arg_through() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG ADGUARDHUB_VERSION" in dockerfile
    assert "ADGUARDHUB_VERSION=${ADGUARDHUB_VERSION}" in dockerfile


def test_the_release_workflow_still_passes_the_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(encoding="utf-8")
    assert "build-args:" in workflow
    assert "ADGUARDHUB_VERSION=${{ steps.version.outputs.version }}" in workflow
