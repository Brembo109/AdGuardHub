# Releases and roadmap

## What each release brought

**v0.1.0** was the MVP: instance management, the central rule model with instant push,
reconciliation with a visible drift log, the aggregated query log, subscription management,
single-user login, and the three notifier types.

**v0.2.0** is what the daily use of it asked for, in roughly that order — full configuration
replication rather than rules alone, version history with diff and rollback, the
AdGuard-compatible `/control` API so phone remotes and Home Assistant can point at the hub,
German alongside English, backup and restore, rate-limited sign-ins, and caps on the tables
that used to grow without end.

**v0.3.0** made the hub say what it knows about itself: update checks against this repository,
a one-click self-update for native installs, and a native installer for Debian and Ubuntu.

**v0.4.0** is mostly about finding things. The top bar dropped from nine entries to seven and
the pages that cover more than one thing grew tabs, so Settings is five linkable pages rather
than six cards stacked down one. Each node now says whether a newer AdGuard Home is waiting for
it — and says so distinctly when it could not be asked, which is not the same as being current.
The hub's own log is readable in the interface, so diagnosing it no longer starts with finding
a shell. The README became a page again, with everything past the quick start moved into these
documentation pages.

> **Do not install v0.4.0 natively.** On Python 3.13 — the default on Debian 13 — it comes up
> with an async database engine and no greenlet to drive it, dies on its first query, and is
> restarted by systemd every five seconds while the installer prints that the hub is running.
> The Docker image is unaffected: it is built on Python 3.12, where the dependency is installed.
> v0.4.1 fixes it.

**v0.4.1** is that fix, and the pipeline changes that should have caught it. greenlet is now a
dependency this project states itself rather than one it hoped to inherit — SQLAlchemy declares
it only for Python below 3.13 — and the installer waits for the hub to answer `/api/health`
before it claims anything, so a crash loop can no longer look like a successful install. CI
tests both Python versions and starts the container rather than only building it. The Updates
card also stopped offering one Docker command to people who never had a compose file.

## Next

In no fixed order: a maintenance mode for pausing reconciliation on one instance while you work
on it, and translating the drift log's summaries (they are generated in the backend and stored
as English text, so they stay English in the German interface).

Deliberately **not** planned before v1.0: per-client rule scoping and multi-user accounts.
v1.0 is when the feature set has settled for daily use, not a particular feature landing.

Support for other DNS filters is **not** on the roadmap. AdGuardHub is an AdGuard Home tool.
The seam for one exists anyway and is worth keeping on its own merits — push, reconcile and
import all reach a node through `DnsAdapter` rather than calling AdGuard's API themselves,
which is what keeps the sync core testable — but nothing is planned behind it, and the rule
syntax is deliberately not abstracted: the hub stores AdGuard-native rules.
