"""In-memory adapter double, standing in for a real AdGuard Home instance."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, ClassVar

from app.adapters.base import AdapterError, DnsAdapter, QueryLogEntry, RemoteFilterList
from app.adapters.sections import SECTION_NAMES


class FakeInstanceState:
    def __init__(self) -> None:
        self.rules: list[str] = []
        self.filter_lists: list[RemoteFilterList] = []
        # Section name -> document, or absent when this fake does not implement it.
        self.sections: dict[str, dict[str, Any]] = {}
        self.query_log: list[QueryLogEntry] = []
        self.offline = False
        self.push_calls = 0
        self.unsupported_sections: set[str] = set()
        self.stats: dict[str, Any] = {}
        # How often the node was actually asked — the cache in front of the
        # aggregation is only worth having if this stops climbing.
        self.stats_calls = 0


class FakeAdapter(DnsAdapter):
    """Every adapter instance for the same base_url shares one state object."""

    name = "fake"
    VERSION = "v0.107.fake"
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
        return self.VERSION

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
        # ``rules_count`` belongs to the node, not to the push: a real AdGuard does
        # not forget how many rules it parsed because the hub renamed a list or
        # toggled it. The hub always sends 0 (it never stores list contents), so
        # replacing wholesale would wipe the counts on every sync.
        held = {(item.kind, item.url): item.rules_count for item in self.state.filter_lists}
        self.state.filter_lists = [
            replace(item, rules_count=held.get((item.kind, item.url), item.rules_count))
            for item in lists
        ]
        self.state.push_calls += 1

    def supported_sections(self) -> tuple[str, ...]:
        return SECTION_NAMES

    async def pull_section(self, name: str) -> dict[str, Any] | None:
        self._guard()
        if name in self.state.unsupported_sections:
            return None
        return dict(self.state.sections.get(name, {})) or None

    async def push_section(self, name: str, data: dict[str, Any]) -> None:
        self._guard()
        if name in self.state.unsupported_sections:
            raise AdapterError(f"{name} is not supported by {self.base_url}", status=404)
        self.state.sections[name] = dict(data)
        self.state.push_calls += 1

    async def stats(self) -> dict[str, Any]:
        self._guard()
        self.state.stats_calls += 1
        return dict(self.state.stats)

    async def query_log(self, limit: int) -> list[QueryLogEntry]:
        self._guard()
        return list(self.state.query_log[:limit])
