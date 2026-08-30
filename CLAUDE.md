# AdGuardHub — Project Specification

## 1. Problem statement

Running two or more AdGuard Home instances for DNS failover (both entered in DHCP, clients
actively switch to instance B when instance A is unreachable) breaks naive A→B config sync
tools: a whitelist entry added on instance B (because a client happened to be routed there)
gets silently overwritten by the next sync from instance A. There is no reliable single place
where "the current filtering truth" lives.

## 2. Core principle

AdGuardHub is the **single source of truth** for all AdGuard Home configuration. The native
AdGuard Home web UIs are no longer used for changes once AdGuardHub is in place — every change
happens in AdGuardHub and is pushed out from there. There is no bidirectional sync and no
merge logic between instances; this eliminates the overwrite race condition structurally
rather than trying to resolve conflicts after the fact.

## 3. Scope (v1)

- **AdGuard Home only.** Pi-hole support is explicitly out of scope for v1, but the sync layer
  must be built behind an adapter interface (`push_rules(instance, ruleset)` /
  `pull_rules(instance)`) so a Pi-hole adapter can be added later without reworking core logic.
- Managed centrally: filtering rules (allow/block, all three AdGuard entry points — see §5),
  blocklist subscription URLs (enable/disable only, not individual domains), and instance-level
  settings (upstream DNS, DoH/DNSSEC, client settings).
- **Not in v1:** per-client rule scoping (all rules are global), a maintenance/emergency mode
  for pausing reconciliation on one instance, multi-user accounts/roles.

## 4. Topology assumptions

- Multiple AdGuard Home instances, entered in DHCP as primary/secondary DNS. Clients fail over
  automatically and unpredictably — propagation of rule changes must be near-real-time, not
  batch/interval-based.
- Deployment target: local network (Unraid/LXC/Docker), same network as the AdGuard instances.
  Not deployed on the external VPS.

## 5. Whitelisting / rule model

Must support all three AdGuard Home mechanisms as UI entry points, all writing into the same
central rule model:

1. Query log "Unblock" action (generates an `@@||domain^` allow rule)
2. Manual custom filtering rules (AdGuard allow/block syntax)
3. The separate Allowlist tab

Rule storage in AdGuardHub is AdGuard-native (not an abstracted superset format), since v1 is
AdGuard-only — see §3 on the adapter interface for future Pi-hole support.

## 6. Sync mechanism

- **Instant push**: every change in AdGuardHub triggers an immediate API call to *all*
  connected instances.
- **Best-effort, no rollback**: if one instance is unreachable, others still receive the
  change immediately; the failed push goes into a retry queue (status: pending / applied /
  failed) and is retried once the instance is reachable again. No waiting for the slowest
  instance, no rollback of successful pushes.
- **Reconciliation job**: runs periodically, compares each instance's actual state against the
  central DB, and auto-corrects drift (e.g. after downtime, or a rule changed directly in the
  native UI despite §2). Every correction is logged and surfaced in the dashboard — never
  silent.
- **No emergency/maintenance mode** in v1: if an instance is manually touched out-of-band, the
  next reconciliation run detects and fixes/logs the drift. This is considered sufficient.

## 7. Initial import

- One existing instance is chosen as the master. Its current AdGuard Home configuration is
  imported wholesale into the central DB as the starting state.
- The other instance(s) are overwritten on first sync. No merge of pre-existing state between
  instances.

## 8. Instance management

- Instances (URL + credentials) are added/removed/disabled dynamically from the AdGuardHub UI
  — no static config file or restart required.
- AdGuard Home has no granular API tokens; store the admin username/password used for
  Basic Auth / session login, encrypted at rest (e.g. Fernet/AES, key from an environment
  variable — never store the encryption key in the DB itself).

## 9. Query log

- Aggregated, near-real-time view across all connected instances in one list, sorted by time,
  with a column identifying which instance logged each entry.
- "Whitelist" action available directly from a log row; writes to the central rule model and
  triggers an instant push to all instances (§6) — regardless of which instance the row came
  from.

## 10. Notifications

Generic, pluggable webhook/notifier system. Configurable in a Settings section, supporting
zero or more simultaneously active targets:

- **Home Assistant** — POST to a `webhook` automation trigger
- **Discord** — Discord incoming webhook URL
- **Gotify** — Gotify REST message API

Events that should fire a notification: reconciliation auto-fix applied, an instance goes
unreachable, a push to an instance fails and enters the retry queue.

## 11. Auth

Single admin user, password hashed with bcrypt, session cookie. No multi-user/roles in v1.
Not intended to be exposed directly to the internet — network-level protection (VPN, internal
only) is the operator's responsibility, not something AdGuardHub needs to enforce itself.

## 12. Tech stack

- **Backend:** Python, FastAPI
- **Frontend:** React, TypeScript
- **DB:** SQLite (rule sets and instance/config data are small; AdGuard's own 700k+-URL
  blocklists are resolved by AdGuard itself — AdGuardHub only tracks the subscription URLs and
  their enabled/disabled state, never the resolved domain lists)
- **Realtime:** WebSocket or SSE for the aggregated query log view
- **Packaging:** single Docker container (backend serves the built frontend as static assets),
  matching the existing Hoardarr pattern

## 13. Repository

- GitHub: `fgrfn/adguardhub` (public, already created)
- Suggested layout:
  ```
  adguardhub/
  ├── backend/        # FastAPI app, adapters/, models/, db/
  ├── frontend/        # React/TS app
  ├── .github/workflows/
  │   ├── ci.yml               # lint + test on push/PR
  │   └── docker-publish.yml   # build & push to ghcr.io on v*.*.* tags
  ├── Dockerfile
  ├── README.md
  └── logo.svg
  ```
- **Versioning:** SemVer starting at `v0.1.0` for the first working MVP. Pre-1.0: breaking
  changes allowed between minor versions. `v1.0.0` once Pi-hole support lands and the feature
  set is considered stable for daily use.
- **CI/CD:** GitHub Actions — lint + test on every push/PR; on every `vX.Y.Z` tag, build and
  publish a Docker image to `ghcr.io/fgrfn/adguardhub` (workflows already scaffolded).

## 14. Explicit non-goals for v1

- Pi-hole support (planned, not built)
- Per-client rule scoping
- Multi-user accounts / roles
- Maintenance mode for individual instances
- Syncing AdGuard infrastructure settings beyond what's listed in §3 as a stretch — start with
  filtering rules and blocklist subscriptions first if time-boxing is needed; upstream
  DNS/DoH/client settings sync can follow once the rule-sync core is solid.

## 15. Definition of done for v0.1.0 (MVP)

- [ ] Add/remove/disable AdGuard Home instances via UI, credentials encrypted at rest
- [ ] Central rule model with instant push to all instances
- [ ] Reconciliation job with visible drift log
- [ ] Aggregated query log view with inline whitelist action
- [ ] Blocklist subscription management (enable/disable, add/remove URL)
- [ ] Single-user login
- [ ] Notification targets: HA, Discord, Gotify webhooks
- [ ] Single Docker image, documented `docker run`/compose example in README
