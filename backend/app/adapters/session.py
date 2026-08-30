"""Shared AdGuard Home session cookies.

AdGuard Home protects its login endpoint against brute force: rejected requests
count toward a limit, and once it trips the instance answers every further attempt
with HTTP 429 for a while — locking AdGuardHub out even though the credentials are
correct.

Adapters are short-lived (the query log poller builds a fresh one every few seconds
for every instance), so a session that lived on the adapter meant re-authenticating
on every single call. Cookies therefore live here instead, keyed by instance and
user, and are reused across adapters.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx

SessionKey = tuple[str, str]

# How long to stay away from an instance's login endpoint after it answers 429.
RATE_LIMIT_COOLDOWN = 60.0


@dataclass
class _Entry:
    cookies: httpx.Cookies | None = None
    blocked_until: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    def __init__(self) -> None:
        self._entries: dict[SessionKey, _Entry] = {}

    def _entry(self, key: SessionKey) -> _Entry:
        entry = self._entries.get(key)
        if entry is None:
            entry = _Entry()
            self._entries[key] = entry
        return entry

    def lock(self, key: SessionKey) -> asyncio.Lock:
        """Serialise logins per instance so concurrent callers make one, not many."""
        return self._entry(key).lock

    def get(self, key: SessionKey) -> httpx.Cookies | None:
        return self._entry(key).cookies

    def set(self, key: SessionKey, cookies: httpx.Cookies) -> None:
        entry = self._entry(key)
        entry.cookies = cookies
        entry.blocked_until = 0.0

    def clear(self, key: SessionKey) -> None:
        self._entry(key).cookies = None

    def note_rate_limited(self, key: SessionKey, cooldown: float = RATE_LIMIT_COOLDOWN) -> None:
        entry = self._entry(key)
        entry.cookies = None
        entry.blocked_until = time.monotonic() + cooldown

    def blocked_for(self, key: SessionKey) -> float:
        """Seconds left on the cooldown, or 0.0 when logins may be attempted."""
        remaining = self._entry(key).blocked_until - time.monotonic()
        return max(0.0, remaining)

    def forget(self, key: SessionKey) -> None:
        self._entries.pop(key, None)

    def reset(self) -> None:
        self._entries.clear()


store = SessionStore()
