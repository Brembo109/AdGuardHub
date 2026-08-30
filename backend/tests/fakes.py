"""In-memory adapter double, standing in for a real AdGuard Home instance."""

from __future__ import annotations

from typing import Any, ClassVar

from app.adapters.base import AdapterError, DnsAdapter, QueryLogEntry, RemoteFilterList


class FakeInstanceState:
    def __init__(self) -> None:
        self.rules: list[str] = []
        self.filter_lists: list[RemoteFilterList] = []
        self.dns: dict[str, Any] = {}
        self.query_log: list[QueryLogEntry] = []
        self.offline = False
        self.push_calls = 0


class FakeAdapter(DnsAdapter):
    """Every adapter instance for the same base_url shares one state object."""

    name = "fake"
    states: ClassVar[dict[str, FakeInstanceState]] = {}

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        *,
        verify_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.state = self.states.setdefault(self.base_url, FakeInstanceState())

    @classmethod
    def reset(cls) -> None:
        cls.states.clear()

    @classmethod
    def state_for(cls, base_url: str) -> FakeInstanceState:
        return cls.states.setdefault(base_url.rstrip("/"), FakeInstanceState())

    def _guard(self) -> None:
        if self.state.offline:
            raise AdapterError(f"{self.base_url} is unreachable")

    async def check(self) -> str:
        self._guard()
        return "v0.107.fake"

    async def pull_rules(self) -> list[str]:
        self._guard()
        return list(self.state.rules)

    async def push_rules(self, rules: list[str]) -> None:
        self._guard()
        self.state.rules = list(rules)
        self.state.push_calls += 1

    async def pull_filter_lists(self) -> list[RemoteFilterList]:
        self._guard()
        return list(self.state.filter_lists)

    async def push_filter_lists(self, lists: list[RemoteFilterList]) -> None:
        self._guard()
        self.state.filter_lists = list(lists)
        self.state.push_calls += 1

    async def pull_dns_settings(self) -> dict[str, Any]:
        self._guard()
        return dict(self.state.dns)

    async def push_dns_settings(self, settings: dict[str, Any]) -> None:
        self._guard()
        self.state.dns = dict(settings)
        self.state.push_calls += 1

    async def query_log(self, limit: int) -> list[QueryLogEntry]:
        self._guard()
        return list(self.state.query_log[:limit])
