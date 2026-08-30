"""Adapter interface every DNS filtering backend must implement.

v1 ships only the AdGuard Home adapter (spec §3), but all core logic talks to this
interface so a Pi-hole adapter can be dropped in without touching sync/reconcile.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AdapterError(RuntimeError):
    """Raised when a backend is unreachable or rejects a request."""


@dataclass(slots=True)
class RemoteFilterList:
    name: str
    url: str
    enabled: bool
    kind: str  # "blocklist" | "allowlist"


@dataclass(slots=True)
class RemoteState:
    """The subset of a backend's configuration that AdGuardHub manages."""

    rules: list[str] = field(default_factory=list)
    filter_lists: list[RemoteFilterList] = field(default_factory=list)
    dns: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QueryLogEntry:
    time: str
    question: str
    question_type: str
    client: str
    answer_status: str
    blocked: bool
    rule: str = ""
    elapsed_ms: float = 0.0
    upstream: str = ""


class DnsAdapter(ABC):
    """Contract for pushing and pulling managed state."""

    name: str = "base"

    @abstractmethod
    async def check(self) -> str:
        """Return a version/identity string, or raise AdapterError."""

    @abstractmethod
    async def pull_rules(self) -> list[str]:
        """Return the backend's current custom filtering rules, in order."""

    @abstractmethod
    async def push_rules(self, rules: list[str]) -> None:
        """Replace the backend's custom filtering rules with ``rules``."""

    @abstractmethod
    async def pull_filter_lists(self) -> list[RemoteFilterList]:
        """Return the backend's subscribed block/allow lists."""

    @abstractmethod
    async def push_filter_lists(self, lists: list[RemoteFilterList]) -> None:
        """Make the backend's subscriptions match ``lists`` exactly."""

    @abstractmethod
    async def pull_dns_settings(self) -> dict[str, Any]:
        """Return the managed instance-level DNS settings."""

    @abstractmethod
    async def push_dns_settings(self, settings: dict[str, Any]) -> None:
        """Apply the managed instance-level DNS settings."""

    @abstractmethod
    async def query_log(self, limit: int) -> list[QueryLogEntry]:
        """Return the most recent query log entries, newest first."""

    async def pull_state(self) -> RemoteState:
        return RemoteState(
            rules=await self.pull_rules(),
            filter_lists=await self.pull_filter_lists(),
            dns=await self.pull_dns_settings(),
        )

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None
