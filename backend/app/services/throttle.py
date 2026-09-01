"""A limit on how fast a password can be guessed.

Every way into the hub ends at bcrypt, which costs about 300 ms per check here.
That is the right price for a login form and it is the only thing that was
slowing an attacker down: nothing counted failures, and nothing ever said no.

Two harms follow from that, and this addresses both by refusing *before* the
hash runs:

* **Guessing.** Unthrottled, a machine on the LAN can work through a password
  list at whatever rate the CPU allows. Ten attempts per five minutes turns that
  from thousands of guesses an hour into a hundred and twenty.
* **Exhaustion.** Each wrong password burns 300 ms of CPU. Since Basic Auth
  arrives on every /control request, an attacker who does not care about getting
  in can spend the hub's cycles instead — and a refusal that still hashes first
  would not help.

Two decisions worth stating, because both could reasonably have gone the other
way and the wrong choice is worse than no throttle at all:

**Counted per source address, never per account.** The hub has exactly one admin.
Locking *the account* after failures would hand any device on the network a way
to lock the operator out of their own hub permanently, which is a denial of
service dressed as a security feature.

**The source is the socket's peer, not X-Forwarded-For.** A header the client
sets is a header the client can vary, and trusting it would let an attacker
issue every request from a fresh imaginary address and never be throttled at
all. Behind a reverse proxy this counts the proxy — the hub belongs on a LAN or
behind a VPN either way, and a throttle that can be bypassed by typing is not
one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Ten wrong passwords in five minutes is far beyond a mistyped one and far below
# anything that makes guessing worthwhile.
MAX_FAILURES = 10
WINDOW_SECONDS = 300.0

# An attacker rotating source addresses would otherwise grow this without limit.
# Well past the number of devices any home network has, and old entries are
# dropped as it fills.
MAX_TRACKED_SOURCES = 4096


@dataclass
class _Attempts:
    count: int = 0
    # When the current window ends; failures before this are what counts.
    expires: float = 0.0


@dataclass
class LoginThrottle:
    """Counts failed sign-ins per source and refuses once there are too many."""

    max_failures: int = MAX_FAILURES
    window: float = WINDOW_SECONDS
    _sources: dict[str, _Attempts] = field(default_factory=dict)

    def retry_after(self, source: str, *, now: float | None = None) -> float:
        """Seconds this source must wait, or 0.0 when it may try again.

        Called before the password is checked, so a locked-out source costs
        nothing beyond a dictionary lookup.
        """
        moment = time.monotonic() if now is None else now
        entry = self._sources.get(source)
        if entry is None:
            return 0.0
        if entry.expires <= moment:
            del self._sources[source]
            return 0.0
        if entry.count < self.max_failures:
            return 0.0
        return entry.expires - moment

    def record_failure(self, source: str, *, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        entry = self._sources.get(source)
        if entry is None or entry.expires <= moment:
            self._evict_expired(moment)
            entry = _Attempts()
            self._sources[source] = entry
        entry.count += 1
        # Each failure restarts the clock, so a steady trickle of guesses does
        # not sit just under the limit forever.
        entry.expires = moment + self.window

    def record_success(self, source: str) -> None:
        """A correct password clears the slate, so a typo costs nothing later."""
        self._sources.pop(source, None)

    def _evict_expired(self, moment: float) -> None:
        if len(self._sources) < MAX_TRACKED_SOURCES:
            return
        for key in [key for key, item in self._sources.items() if item.expires <= moment]:
            del self._sources[key]
        if len(self._sources) >= MAX_TRACKED_SOURCES:
            # Everything tracked is still live: drop whatever expires soonest
            # rather than refuse to track the newest source.
            oldest = min(self._sources, key=lambda key: self._sources[key].expires)
            del self._sources[oldest]
