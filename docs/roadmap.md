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

**v0.4.2** hardens the command this project invites people to pipe into a root shell. `curl`
without `-f` prints the server's error body and exits zero, so a URL that answers "Not Found"
sends those words to `sh`, which tries to run them. Every documented form now passes `-f`, and
the install one-liner points back at `raw.githubusercontent.com` — the shorter domain in front
of it turned out to serve nothing, which is how the missing flag was noticed.

**v0.4.3** ends a loop that had been running since the first two-node install. Reconciliation
compared the hub's `time_zone: "Local"` against a node's `Europe/Berlin` and called it drift,
corrected it by sending `Local` again, and found the same difference on the next run — every few
minutes, forever, writing a drift event and firing a notification each time. `Local` is not a
zone but an instruction to use the node's own, so the comparison was holding a request next to
its answer. Only nodes whose clock knows where they are were affected, which is why it showed on
one node of two.

Alongside that: `docker run` is no longer a supported way in — everything the compose file
carries lives in shell history when you start a container that way — and the installation docs
now say which side of the volume mount is yours to choose, and to open the hub at the host's
address rather than at localhost.

**v0.4.4** is about the release pipeline rather than the hub. The published image name is
written down instead of derived from the repository — renaming this repository would otherwise
have started publishing to a different GHCR package while every existing `docker compose pull`
kept pointing at the old one, which stops receiving updates without ever failing. And the
release now carries a `SHA256SUMS` that the installer checks before unpacking a tarball into
`/opt` as root. That check catches a truncated download or the wrong mirror, not a compromised
GitHub — the sums travel from the same place as the archive, and defending against that needs a
signature checked against a key held in advance, which this project does not publish.

**v0.4.5** brought maintenance mode, which had been written down as a v1 non-goal twice.
Working on a node used to mean fighting the hub: a push overwrote what you had just done, and
reconciliation put it back within five minutes. The only lever was disabling the instance, which
also makes the hub forget what it still owes that node. Maintenance stops pushes and
reconciliation for one instance while queueing what it misses, so releasing it replays the queue
at once rather than waiting for the retry timer. A feature in a patch release is not what
SemVer intends; it went out that way because it was the fix to a problem in front of us, and the
number is left as it was rather than rewritten after the fact.

**v0.5.0** is the first minor since the 0.4 line settled, and both halves are about a number the
interface was not showing.

The drift log can now be cleared. A drift entry had no way out — once written it stayed until
the 500-row cap pushed it off the end — which is right while a finding is live and wrong once
its cause is gone, as with the time-zone loop above that filled the log with a fault that never
existed. The confirmation says what the button does not do: deleting the record does not resolve
anything, and a node that still disagrees is found again on the next run. The retry queue
deliberately gets no such button, because a pending job is work still owed to an instance.

Filter lists now show how many rules each subscription holds, and the active total. The hub
never stores the contents of a list, so it cannot answer that from its own database — the
numbers come back from the nodes, and the interface says so where that matters: a list no node
has fetched yet shows a dash rather than a zero, an unreachable fleet means the sizes are
unknown rather than empty, and two nodes reporting different sizes (they refresh on their own
schedules) is marked and broken down per node rather than averaged into one number. None of it
reaches reconciliation: a rule count is an observation about a file, not configuration the hub
owns, so a difference in one is never drift.

**v0.6.0** fixes the update button on any hub that had already updated once. Pressing it
appeared to do nothing: the confirmation closed and an ordinary idle button came back, with no
progress and no log. The upgrade was running the whole time — a browser reload a few minutes
later showed the new version — but nothing said so, and pressing again hit a hub that was
already restarting, which is where the `failed to fetch` came from.

The updater truncates its log when it starts, so between the press and the systemd path unit
firing, the only log on disk is the previous upgrade's, still ending in its own `[exit 0]`. The
hub read that marker as this run's outcome, reported the request as neither running nor
finished, and the interface never began watching. A fresh install has no such log, which is why
the fault only ever appeared from the second upgrade onward. A log is now attributed to the
previous run when it is older than the request, not only when it is older than fifteen minutes.

Alongside it, the release notice grew the counterpart it was missing. The banner announcing a
new version is dismissible on purpose — a bar you cannot get rid of teaches you to stop reading
bars — but dismissing it used to make the release invisible, leaving only a settings page you
had to already suspect. A dot now sits beside *Settings* in the top bar for as long as a newer
release exists: not dismissible, never in the way, gone when the hub is current. The
interruption and the standing fact are two different things rather than one thing asked to be
both.

## Next

Translating the drift log's summaries: they are generated in the backend and stored as English
text, so they stay English in the German interface.

Deliberately **not** planned before v1.0: per-client rule scoping and multi-user accounts.
v1.0 is when the feature set has settled for daily use, not a particular feature landing.

Support for other DNS filters is **not** on the roadmap. AdGuardHub is an AdGuard Home tool.
The seam for one exists anyway and is worth keeping on its own merits — push, reconcile and
import all reach a node through `DnsAdapter` rather than calling AdGuard's API themselves,
which is what keeps the sync core testable — but nothing is planned behind it, and the rule
syntax is deliberately not abstracted: the hub stores AdGuard-native rules.
