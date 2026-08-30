"""AdGuard Home adapter, speaking the /control REST API."""

from __future__ import annotations

from typing import Any

import httpx

from .base import AdapterError, DnsAdapter, QueryLogEntry, RemoteFilterList

# AdGuard's query log "reason" values that mean the answer was actually filtered.
_ALLOWED_REASONS = {"NotFilteredWhiteList", "NotFilteredNotFound", "NotFilteredError", ""}

# Managed keys of /control/dns_info. Anything else on the instance is left alone.
DNS_KEYS = (
    "upstream_dns",
    "bootstrap_dns",
    "fallback_dns",
    "upstream_mode",
    "dnssec_enabled",
    "protection_enabled",
)


class AdGuardAdapter(DnsAdapter):
    name = "adguard"

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        *,
        verify_tls: bool = True,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            verify=verify_tls,
            timeout=timeout,
            follow_redirects=True,
        )
        self._logged_in = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- transport -------------------------------------------------------

    async def _login(self) -> None:
        """Establish a session cookie for builds that reject HTTP Basic auth."""
        if not self._username:
            raise AdapterError("Authentication required but no credentials are configured")
        try:
            response = await self._client.post(
                "/control/login",
                json={"name": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise AdapterError(f"Login failed: {exc}") from exc
        if response.status_code >= 400:
            raise AdapterError(f"Login rejected with HTTP {response.status_code}")
        self._logged_in = True

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        auth = (self._username, self._password) if self._username and not self._logged_in else None
        try:
            response = await self._client.request(method, path, auth=auth, **kwargs)
            if response.status_code in (401, 403) and self._username and not self._logged_in:
                await self._login()
                response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise AdapterError(f"{method} {path} failed: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text.strip()[:200]
            raise AdapterError(f"{method} {path} returned HTTP {response.status_code}: {detail}")
        return response

    async def _get_json(self, path: str, **kwargs: Any) -> Any:
        response = await self._request("GET", path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterError(f"GET {path} returned a non-JSON body") from exc

    # -- DnsAdapter ------------------------------------------------------

    async def check(self) -> str:
        data = await self._get_json("/control/status")
        version = data.get("version") if isinstance(data, dict) else None
        return str(version or "unknown")

    async def pull_rules(self) -> list[str]:
        data = await self._get_json("/control/filtering/status")
        raw = data.get("user_rules") or []
        return [str(line) for line in raw]

    async def push_rules(self, rules: list[str]) -> None:
        await self._request("POST", "/control/filtering/set_rules", json={"rules": rules})

    async def pull_filter_lists(self) -> list[RemoteFilterList]:
        data = await self._get_json("/control/filtering/status")
        result: list[RemoteFilterList] = []
        for key, kind in (("filters", "blocklist"), ("whitelist_filters", "allowlist")):
            for item in data.get(key) or []:
                result.append(
                    RemoteFilterList(
                        name=str(item.get("name") or item.get("url") or ""),
                        url=str(item.get("url") or ""),
                        enabled=bool(item.get("enabled")),
                        kind=kind,
                    )
                )
        return result

    async def push_filter_lists(self, lists: list[RemoteFilterList]) -> None:
        """Reconcile subscriptions to ``lists``: add missing, update changed, drop extras."""
        current = {(item.kind, item.url): item for item in await self.pull_filter_lists()}
        desired = {(item.kind, item.url): item for item in lists}

        for key, item in desired.items():
            whitelist = item.kind == "allowlist"
            existing = current.get(key)
            if existing is None:
                await self._request(
                    "POST",
                    "/control/filtering/add_url",
                    json={"name": item.name, "url": item.url, "whitelist": whitelist},
                )
                if not item.enabled:
                    await self._set_url(item, whitelist)
            elif existing.enabled != item.enabled or existing.name != item.name:
                await self._set_url(item, whitelist)

        for key, item in current.items():
            if key not in desired:
                await self._request(
                    "POST",
                    "/control/filtering/remove_url",
                    json={"url": item.url, "whitelist": item.kind == "allowlist"},
                )

    async def _set_url(self, item: RemoteFilterList, whitelist: bool) -> None:
        await self._request(
            "POST",
            "/control/filtering/set_url",
            json={
                "url": item.url,
                "whitelist": whitelist,
                "data": {"name": item.name, "url": item.url, "enabled": item.enabled},
            },
        )

    async def pull_dns_settings(self) -> dict[str, Any]:
        data = await self._get_json("/control/dns_info")
        if not isinstance(data, dict):
            return {}
        return {key: data[key] for key in DNS_KEYS if key in data}

    async def push_dns_settings(self, settings: dict[str, Any]) -> None:
        payload = {key: value for key, value in settings.items() if key in DNS_KEYS}
        if not payload:
            return
        await self._request("POST", "/control/dns_config", json=payload)

    async def query_log(self, limit: int) -> list[QueryLogEntry]:
        data = await self._get_json("/control/querylog", params={"limit": limit})
        rows = data.get("data") if isinstance(data, dict) else None
        entries: list[QueryLogEntry] = []
        for row in rows or []:
            entries.append(self._parse_log_row(row))
        return entries

    @staticmethod
    def _parse_log_row(row: dict[str, Any]) -> QueryLogEntry:
        question = row.get("question") or {}
        reason = str(row.get("reason") or "")
        rules = row.get("rules") or []
        rule_text = ""
        if rules and isinstance(rules[0], dict):
            rule_text = str(rules[0].get("text") or "")
        elif row.get("rule"):
            rule_text = str(row["rule"])
        try:
            elapsed = float(row.get("elapsed_ms") or 0)
        except (TypeError, ValueError):
            elapsed = 0.0
        return QueryLogEntry(
            time=str(row.get("time") or ""),
            question=str(question.get("name") or question.get("host") or ""),
            question_type=str(question.get("type") or ""),
            client=str(row.get("client") or ""),
            answer_status=reason,
            blocked=reason not in _ALLOWED_REASONS,
            rule=rule_text,
            elapsed_ms=elapsed,
            upstream=str(row.get("upstream") or ""),
        )
