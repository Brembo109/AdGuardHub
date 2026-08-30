"""The AdGuard Home adapter, driven against a mocked /control API."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.adguard import AdGuardAdapter
from app.adapters.base import AdapterError, RemoteFilterList

FILTERING_STATUS = {
    "enabled": True,
    "user_rules": ["||ads.example.com^", "@@||shop.example.com^"],
    "filters": [
        {"url": "https://example.com/block.txt", "name": "Block", "enabled": True, "id": 1}
    ],
    "whitelist_filters": [
        {"url": "https://example.com/allow.txt", "name": "Allow", "enabled": False, "id": 2}
    ],
}


def make_adapter(handler, **kwargs) -> AdGuardAdapter:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://adguard.local", transport=transport)
    return AdGuardAdapter("http://adguard.local", "admin", "pw", client=client, **kwargs)


async def test_check_reads_the_version() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/control/status"
        return httpx.Response(200, json={"version": "v0.107.55"})

    assert await make_adapter(handler).check() == "v0.107.55"


async def test_pull_rules_and_filter_lists() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FILTERING_STATUS)

    adapter = make_adapter(handler)
    assert await adapter.pull_rules() == ["||ads.example.com^", "@@||shop.example.com^"]

    lists = await adapter.pull_filter_lists()
    assert [(item.kind, item.enabled) for item in lists] == [
        ("blocklist", True),
        ("allowlist", False),
    ]


async def test_push_rules_replaces_the_whole_set() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/control/filtering/set_rules"
        seen["body"] = request.content
        return httpx.Response(200, json={})

    await make_adapter(handler).push_rules(["||a.com^"])
    assert b'"rules"' in seen["body"]
    assert b"||a.com^" in seen["body"]


async def test_push_filter_lists_adds_updates_and_removes() -> None:
    calls: list[tuple[str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/control/filtering/status":
            return httpx.Response(200, json=FILTERING_STATUS)
        import json

        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={})

    desired = [
        # unchanged
        RemoteFilterList("Block", "https://example.com/block.txt", True, "blocklist"),
        # newly added
        RemoteFilterList("Extra", "https://example.com/extra.txt", True, "blocklist"),
        # the allowlist subscription is dropped entirely
    ]
    await make_adapter(handler).push_filter_lists(desired)

    paths = [path for path, _ in calls]
    assert "/control/filtering/add_url" in paths
    assert "/control/filtering/remove_url" in paths
    removed = next(body for path, body in calls if path.endswith("remove_url"))
    assert removed == {"url": "https://example.com/allow.txt", "whitelist": True}


async def test_query_log_parsing_marks_blocked_entries() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "time": "2026-01-01T10:00:00Z",
                        "question": {"name": "ads.example.com", "type": "A"},
                        "client": "192.168.1.10",
                        "reason": "FilteredBlackList",
                        "elapsed_ms": "1.5",
                        "rules": [{"text": "||ads.example.com^"}],
                    },
                    {
                        "time": "2026-01-01T10:00:01Z",
                        "question": {"name": "shop.example.com", "type": "A"},
                        "client": "192.168.1.11",
                        "reason": "NotFilteredWhiteList",
                        "elapsed_ms": "bogus",
                    },
                ]
            },
        )

    entries = await make_adapter(handler).query_log(100)
    assert entries[0].blocked is True
    assert entries[0].rule == "||ads.example.com^"
    assert entries[0].elapsed_ms == 1.5
    assert entries[1].blocked is False
    assert entries[1].elapsed_ms == 0.0


async def test_dns_settings_are_limited_to_managed_keys() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/control/dns_info":
            return httpx.Response(
                200,
                json={
                    "upstream_dns": ["1.1.1.1"],
                    "dnssec_enabled": True,
                    "ratelimit": 20,  # not managed by AdGuardHub
                },
            )
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    adapter = make_adapter(handler)
    assert await adapter.pull_dns_settings() == {
        "upstream_dns": ["1.1.1.1"],
        "dnssec_enabled": True,
    }

    await adapter.push_dns_settings({"upstream_dns": ["9.9.9.9"], "ratelimit": 99})
    assert captured["body"] == {"upstream_dns": ["9.9.9.9"]}


async def test_a_401_triggers_a_session_login_and_retries() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/control/login":
            return httpx.Response(200, json={})
        if seen.count("/control/status") == 1:
            return httpx.Response(401, text="unauthorised")
        return httpx.Response(200, json={"version": "v0.107.55"})

    assert await make_adapter(handler).check() == "v0.107.55"
    assert seen == ["/control/status", "/control/login", "/control/status"]


async def test_http_errors_surface_as_adapter_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(AdapterError, match="500"):
        await make_adapter(handler).check()


async def test_transport_errors_surface_as_adapter_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AdapterError, match="connection refused"):
        await make_adapter(handler).check()
