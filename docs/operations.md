# Running it

- [Logs](#logs)
- [Backup and restore](#backup-and-restore)
- [Notifications](#notifications)
- [Security](#security)

## Logs

Two different things are called a log here, and they are not the same:

- **The query log** is DNS traffic — what your clients asked for, aggregated across every
  instance. It lives in the UI and is what you use day to day.
- **The application log** is the hub talking about itself: what it did on start, a push that
  failed, a wrong password. It goes to stderr, so `docker logs adguardhub` (or
  `docker compose logs -f`) reads it back.

The last 500 lines are also readable in the interface under *Settings → Log*, which follows
along live. That is a window, not a replacement: it lives in memory, is cleared on restart, and
your container or systemd log remains the record. Its own polling is deliberately left out of
it, so watching the log does not push what you came to read out of the buffer.

At the default `INFO` you get startup, schema migrations, notification failures, and
sign-ins. `ADGUARDHUB_LOG_LEVEL=DEBUG` adds the per-instance diagnostics — why a node's stats
came back empty, why a query log poll returned nothing — which is what you want while something
is misbehaving and nothing but noise the rest of the time. It also turns on the HTTP client's
own narration, which is verbose: on a hub polling two nodes it accounts for the large majority
of all output.

**Sign-ins are logged.** A wrong password writes a `WARNING` naming the source address and
which door was knocked on (the hub's login form, the AdGuard-compatible one, or Basic Auth),
and the attempt that trips the rate limit says so once. The attempted username is deliberately
not logged: with a single admin account it tells you nothing you don't know, and logging it
would write a password to disk the first time someone types one into the wrong box.

Set `ADGUARDHUB_LOG_FILE=/data/adguardhub.log` to also keep a rotating file (5 MB, three
backups by default). Most deployments do not need it — the container runtime already keeps a
copy — but it survives `docker rm` and is easier to hand to someone else. If the path cannot
be written, the hub says so and carries on with stderr rather than refusing to start.

Docker's default json-file driver keeps that copy **without any size limit**, which on a
long-running hub is a disk that fills quietly. The Compose example caps it; if you use
`docker run`, add the same:

```
--log-opt max-size=10m --log-opt max-file=3
```

## Backup and restore

Everything the hub owns lives in one SQLite file, so *Settings → Backup* offers it as a
single JSON document: rules, subscriptions, instance settings, and the list of instances.

```bash
curl -u admin:yourpassword http://adguardhub.lan/api/backup -o adguardhub-backup.json
```

**Instance passwords are never in it.** A backup is downloaded through a browser and then
lives wherever you put it; ciphertext would be no better, since it is one leaked key away
from the plaintext — and by default that key sits in the same directory as the database it
protects. Restored instances therefore come back needing their password typed in again, and
the restore says how many.

That is also why this JSON file is *not* a substitute for backing up `/data`: it deliberately
leaves out the credentials, so restoring from it always costs you a round of retyping. A copy
of the data directory — database and `secret.key` together — restores everything.

Restoring replaces the hub's rules, subscriptions and instance settings and pushes the
result to every node. Two things make that safe to try: the file is validated in full
*before* anything is written, so a wrong file leaves the hub untouched; and the state it
replaces stays in the version history, so a restore is undone by rolling back to it.

A node already connected keeps its credentials — a restore adds what is missing rather
than overwriting what works.

## Notifications

Configure any number of webhook targets under *Settings → Notifications*. Each can subscribe to
specific events or to all of them:

| Event | Fires when |
| --- | --- |
| `reconcile.fixed` | Reconciliation found (and corrected) drift on an instance |
| `instance.unreachable` | An instance stopped responding |
| `instance.recovered` | An instance started responding again |
| `push.failed` | A push failed and went into the retry queue |

The two instance events are **edge-triggered**: one message when a node goes,
one when it comes back, however long the outage lasts and however often the hub
polls in between. A target that subscribes to *all* events picks the new one up
automatically; a target that lists its events explicitly has to add it, since
silently widening a subscription you configured would be the wrong default.

- **Home Assistant** — point it at `http://<ha>:8123/api/webhook/<id>` and trigger an automation
  on that webhook. The JSON body carries `event`, `title` and `message`.
- **Discord** — paste an incoming webhook URL.
- **Gotify** — use `https://<gotify>/message` and put the application token in the token field.

## Security

AdGuardHub is meant to run **inside your network**, alongside the AdGuard instances. It has a
single admin account (bcrypt-hashed password, signed session cookie) and no multi-user model.
Exposing it to the internet is not a supported deployment — put it behind a VPN or keep it on the
LAN.

Sign-ins are rate limited: ten failed attempts from one address within five minutes are answered
with `429` and a `Retry-After` until the window passes. The limit is shared by all three ways in
— the login form, `/control/login` and Basic Auth — and is applied *before* the password is
hashed, so a locked-out source costs a dictionary lookup rather than the ~300 ms bcrypt spends.

Failures are counted **per source address, never per account**. With one admin, locking the
account would hand any device on the network a way to lock you out of your own hub. For the same
reason the source is the connection's peer and not `X-Forwarded-For`: a header the client sets is
a header the client can vary. Behind a reverse proxy that means attempts are counted against the
proxy.

The AdGuard admin passwords the hub stores are encrypted at rest, with the key held outside the
database — see [The encryption key](install.md#the-encryption-key).
