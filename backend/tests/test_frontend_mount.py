"""The SPA fallback that serves the built frontend from the same container."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.main import mount_frontend


def build_app(tmp_path, monkeypatch) -> FastAPI:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>AdGuardHub</title>")
    (static / "assets" / "app.js").write_text("console.log('hi')")
    (static / "logo.svg").write_text("<svg/>")

    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_STATIC_DIR", str(static))
    app = FastAPI()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    mount_frontend(app)
    return app


async def test_spa_serves_assets_and_falls_back_to_index(tmp_path, monkeypatch) -> None:
    app = build_app(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/health")).json() == {"status": "ok"}

        # A real file is served as-is.
        assert (await client.get("/logo.svg")).text == "<svg/>"
        assert (await client.get("/assets/app.js")).status_code == 200

        # Client-side routes fall back to index.html.
        for path in ("/", "/rules", "/instances"):
            response = await client.get(path)
            assert response.status_code == 200
            assert "AdGuardHub" in response.text

        # Unknown API paths must 404 rather than return the SPA shell.
        assert (await client.get("/api/nope")).status_code == 404

    get_settings.cache_clear()


async def test_no_static_dir_leaves_the_api_alone(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ADGUARDHUB_STATIC_DIR", str(tmp_path / "missing"))
    app = FastAPI()
    mount_frontend(app)
    assert not any(getattr(route, "path", "") == "/{path:path}" for route in app.routes)
    get_settings.cache_clear()


async def test_index_is_revalidated_but_hashed_assets_are_not(tmp_path, monkeypatch) -> None:
    """The caching rule that decides whether an upgrade lands or blanks the page.

    index.html names its scripts by content hash and an upgrade deletes the old
    ones, so a browser allowed to reuse a stale index.html asks for bundles that
    are gone and renders nothing — while the hub is up and answering. Without a
    Cache-Control header a browser may invent its own freshness (RFC 9111
    §4.2.2), which is exactly how that happened.
    """
    app = build_app(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ("/", "/rules"):
            assert (await client.get(path)).headers["cache-control"] == "no-cache"

        # Unhashed files are named the same across builds, so they revalidate too.
        assert (await client.get("/logo.svg")).headers["cache-control"] == "no-cache"

        # The hashed bundles are the opposite case: a name never outlives its
        # contents, so refetching them on every load would be pure waste.
        assets = (await client.get("/assets/app.js")).headers["cache-control"]
        assert "immutable" in assets
        assert "max-age=31536000" in assets

    get_settings.cache_clear()


async def test_a_missing_asset_is_a_plain_404(tmp_path, monkeypatch) -> None:
    """It must not fall back to index.html: a bundle request answered with HTML
    is a syntax error in the console rather than a legible failure."""
    app = build_app(tmp_path, monkeypatch)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/index-OLDHASH.js")
        assert response.status_code == 404
        assert "cache-control" not in response.headers

    get_settings.cache_clear()
