# Installing AdGuardHub

Two ways in: a container with Docker Compose, or a native systemd service. Either way the
admin account is created in the browser on first open — nothing is configured up front.

- [Docker Compose](#docker-compose)
- [Without Docker (Debian / Ubuntu)](#without-docker-debian--ubuntu)
- [File permissions (PUID / PGID)](#file-permissions-puid--pgid)
- [The encryption key](#the-encryption-key)
- [First run](#first-run)
- [Staying up to date](#staying-up-to-date)

## Docker Compose

Save this as **`docker-compose.yml`** in a directory of your choice. That directory becomes the
hub's home: `docker compose` reads the file from the directory it is run in, so every command
here — including the upgrade later on — belongs inside it.

```yaml
services:
  adguardhub:
    image: ghcr.io/fgrfn/adguardhub:latest
    container_name: adguardhub
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./data:/data
    environment:
      PUID: "1000"   # Unraid: 99
      PGID: "1000"   # Unraid: 100
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

```bash
docker compose up -d
```

Then open the hub at `http://<host>` — the address of the machine you started it on, not the one
you are browsing from — and create the admin account. Published on another port, it is
`http://<host>:8080`.

### Where the data goes

`./data:/data` is two different things either side of the colon. The right-hand `/data` is a path
*inside* the container and never appears on your host; the left-hand side is yours to choose, and
it is the directory you will be backing up. Relative, as above, it sits next to the compose file —
self-contained, and a move is "copy the folder". An absolute path is the better answer once this
is a permanent installation, because it does not depend on where you happen to be standing:

```yaml
- /mnt/user/appdata/adguardhub:/data   # Unraid
- /srv/adguardhub/data:/data           # /srv is where service data belongs
- /var/lib/adguardhub:/data            # the same path the native installer uses
```

The last one is worth a thought: pick it and the hub's data lives at the same place whichever way
it was installed, so your backup rule is one line rather than two, and moving from the container
to the native install later means the database is already where the service looks for it. The one
thing that move still needs is ownership — the container writes as `PUID:PGID`, the service runs
as `adguardhub`, so `chown -R adguardhub:adguardhub /var/lib/adguardhub` before starting it.

Whatever you choose, back up that directory as a whole. It holds `adguardhub.db` **and**
`secret.key`, and one without the other cannot read your stored instance passwords.

The container listens on **port 80**. If the host already serves something there,
publish it elsewhere — `"8080:80"` — the container-side port stays 80.

The `logging:` block is not decoration either. Docker's default driver keeps every line the
container has ever written, without limit, which on a hub that runs for months is a disk that
fills quietly — see [Logs](operations.md#logs).

**A bare `docker run` is not a supported way to install this.** It works, but everything the
compose file carries — the volume, the log caps, the restart policy, the port mapping — then
lives only in your shell history, and the upgrade a year later is a command nobody can
reconstruct. Compose keeps that in a file you can read.

## Without Docker (Debian / Ubuntu)

For an LXC container, a VM or a Raspberry Pi, `install.sh` sets up AdGuardHub as a systemd
service. Read it before you run it — it runs as root:

```bash
curl -fsSL https://raw.githubusercontent.com/fgrfn/adguardhub/main/install.sh -o install.sh
less install.sh
sudo sh install.sh
```

Or in one line, if you would rather not:

```bash
curl -fsSL https://raw.githubusercontent.com/fgrfn/adguardhub/main/install.sh | sudo sh
```

The `-f` is not decoration. Without it curl hands the server's error page to the shell on the
other side of the pipe, which then tries to run it as commands — a missing script becomes
`sh: 1: Not: not found` in a root shell rather than an honest failure. With `-f`, curl exits
non-zero and writes nothing, so `sh` gets an empty script and does nothing at all.

The script comes from `main` but installs the newest **release**, not the current state of the
branch. It creates an `adguardhub` system user, installs to `/opt/adguardhub`, puts the database
in `/var/lib/adguardhub`, and starts the service. It asks nothing: the admin account is created
in the browser, and the encryption key looks after itself (see [The encryption key](#the-encryption-key)).

| | |
| --- | --- |
| Settings | `/etc/adguardhub/adguardhub.env` — every `ADGUARDHUB_*` variable works here |
| Data | `/var/lib/adguardhub` — **back this up**, it holds the database and the key |
| Logs | `journalctl -u adguardhub -f` |
| Upgrade | re-run the installer; your data and settings are left alone |
| Remove | `systemctl disable --now adguardhub`, then delete `/opt/adguardhub`, `/var/lib/adguardhub`, `/etc/adguardhub` and `/etc/systemd/system/adguardhub.service` |

A different port, or a specific version:

```bash
ADGUARDHUB_PORT=8080 sudo -E sh install.sh
ADGUARDHUB_VERSION=v0.3.0 sudo -E sh install.sh
```

The service runs unprivileged, with `ProtectSystem=strict` and write access to nothing but its
own data directory. Binding port 80 as a non-root user comes from `CAP_NET_BIND_SERVICE`, which
is the only capability it keeps.

**Debian and Ubuntu with systemd only.** On anything else the script stops and says so rather
than half-installing — use the Docker image, which has no such requirement.

## File permissions (PUID / PGID)

A bind mount keeps the *host* directory's ownership, so the container has to run as a
user that may write there. Set `PUID`/`PGID` to whoever owns the mounted directory:

| Platform | PUID | PGID |
| --- | --- | --- |
| Unraid | `99` | `100` |
| Most Linux hosts (first user) | `1000` | `1000` |

The container starts as root only long enough for its entrypoint to `chown /data`, then
drops to `PUID:PGID` for the application itself. If the directory still isn't writable,
startup aborts with a single line naming the directory, the uid it tried, and the fix —
rather than a SQLAlchemy traceback.

## The encryption key

AdGuardHub encrypts the AdGuard admin passwords it stores, and signs your session cookie, with
one master key. **You do not have to set it.** On first start, with no `ADGUARDHUB_SECRET_KEY`
in the environment, the hub generates a strong one and keeps it at `/data/secret.key` (mode
`0600`). Updates, restarts and container rebuilds then leave your instance credentials intact.

Setting the variable yourself is still the better option, and it is what the examples above
leave room for: a key you supply lives *outside* the directory it protects, so a copy of `/data`
alone is not enough to read the passwords. Generate one with `openssl rand -base64 48`.

> **Whichever you choose, the key and the database belong together.** Back up `secret.key`
> alongside `adguardhub.db`, or set the variable and remember it. A key that is lost or changed
> makes the stored instance passwords unreadable — the hub keeps working and asks you to type
> them in again.

**Never paste an example key.** A key published in a README or a compose file is worse than no
key at all: the hub starts, looks healthy, warns about nothing, and protects nothing, because
anyone can read the key and decrypt the database. AdGuardHub therefore refuses to start when it
finds one of its own documented placeholders, and says what to do instead.

## First run

1. **Add your instances** under *Instances* — base URL plus the AdGuard Home admin
   username/password. AdGuard has no granular API tokens, so it's the admin account or nothing;
   the password is encrypted before it's stored and is never sent back to the browser.
2. **Pick a master** and hit *Import as master*. Its rules and subscriptions become the hub's
   starting state, and every other instance is overwritten with it on the next push. There is no
   merge between instances — that's the whole point.

   Naming a master is not compulsory. Skip the step and the hub starts from an empty rule set,
   which you then fill in here: settings you never touch stay switched off for replication, so
   an area the hub has no opinion about is left to each node rather than being flattened by an
   empty document. Import is the shortcut when one node already holds the configuration you
   want; it is not the only way in.
3. **Work only in AdGuardHub from here on.** Anything changed directly in a native AdGuard UI is
   detected by the next reconciliation run, corrected, and shown in the drift log.

## Staying up to date

The hub asks GitHub what the newest release is, at most once every few hours, and says so in a
banner and under *Settings → Updates* when it is behind. That request goes to `api.github.com`
and carries nothing about your hub — no version, no identifier, no telemetry of any kind. It is
one plain `GET` of the public releases endpoint, and the answer is cached so that opening the
interface does not mean asking again.

A hub on a network with no route out is not broken by this: the failed check is reported in the
Updates card as a check that got no answer, retried in a few minutes rather than a few hours,
and nothing else. To stop it entirely, untick *Check for new releases* — or start with
`ADGUARDHUB_UPDATE_CHECK=false`, which seeds the setting on a fresh database.

**Applying the update depends on how you installed**, so the card shows the one that matches:

| Installed as | Upgrade with |
| --- | --- |
| Docker | `docker compose pull && docker compose up -d`, from the directory holding your `docker-compose.yml` — a container cannot replace its own image; your data volume is untouched |
| Native (`install.sh`) | the **Update this hub** button, or re-run the installer yourself; either way it upgrades in place and never touches your data directory or `adguardhub.env` |
| A checkout | whatever you normally do with that checkout |

`docker compose` reads its file from the directory it runs in. Run it somewhere else and it
answers `no configuration file provided: not found`, which is about the directory rather than
about the hub.

If that message appears because the container was started without compose at all, this is the
moment to move it onto one. Write the compose file above, point its `volumes:` at the directory
the running container already uses, then:

```bash
docker rm -f adguardhub
docker compose up -d
```

Nothing is lost in the swap: the database and the encryption key live in that directory, not in
the container.

`docker compose up -d` on its own will **not** fetch a newer image: Docker reuses the cached one
whenever the tag already exists locally. To run your own checkout instead of the published
image, `docker compose up -d --build` builds from the working tree. Either way, the first log
line tells you what you got:

```bash
docker logs adguardhub 2>&1 | head -5
# INFO adguardhub: AdGuardHub 0.2.0 starting as uid=1000 gid=1000, data dir /data
```

The same version is on `GET /api/health` and in the footer under every page, which is usually
the faster answer to "did the update land?". A published image reports the release tag it was
built from; one you built yourself reports `dev`, because it was not cut from a tag and should
not claim to have been.

### The update button, and why it is safe

A native install can be told to upgrade itself from the interface. The hub does not do the
upgrading — it holds none of the privilege that would take, and is not given any.

It runs as its own unprivileged user under `ProtectSystem=strict`: it cannot write to `/opt`,
cannot restart itself, and has no sudo rule. An update button is not a good enough reason to
change that, so instead the hub creates **one empty file** in its own data directory. A systemd
path unit (`adguardhub-update.path`) watches for that file, and a root oneshot unit
(`adguardhub-update.service`) does the privileged half: it fetches `install.sh` over https from
this repository and runs it, exactly as you would by hand.

The trigger file is empty on purpose. It carries no version, no URL and no arguments, so the
worst anyone with your admin password can cause through it is *the newest official release,
from GitHub, over TLS* — the same thing that got installed in the first place. The file is
removed before the upgrade starts, so a failure waits for a person rather than looping.

The updater writes its output to `update.log` in the data directory, which is what the progress
view in the interface is reading; the hub is stopped and restarted partway through, so that log
is the only place the state can survive. If the upgrade fails, nothing is rolled back and the
hub keeps running the version it had.

Your nodes keep answering DNS throughout — they do not depend on the hub to resolve.

Hubs installed before this existed write a file nothing is watching. The interface says so
rather than spinning forever: re-run the installer once by hand, and the button works from then
on.
