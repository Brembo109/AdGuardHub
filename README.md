<p align="center">
  <img src="./logo.svg" width="140" alt="AdGuardHub logo" />
</p>

<h1 align="center">AdGuardHub</h1>

<p align="center">
  One dashboard to manage multiple AdGuard&nbsp;Home instances as a single system.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-in%20development-yellow" alt="status" />
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license" />
  <img src="https://img.shields.io/badge/stack-FastAPI%20%2B%20React-4C9A6A" alt="stack" />
</p>

---

## The problem

If you run more than one AdGuard Home instance for DNS failover, you've probably hit this: a client fails over to instance **B**, you whitelist a domain there, and the next config sync from instance **A** silently overwrites it. Simple A→B sync tools only push config in one direction — they don't know (or care) that the whitelist you just added is the one that matters.

**AdGuardHub** fixes this by removing the need to sync between instances at all.

## How it works

AdGuardHub becomes the **single source of truth** for filtering rules, blocklist subscriptions, and instance settings. You never touch the native AdGuard UI again — every change goes through the hub and is pushed to **all** connected instances at once.

- **Instant push** on every change, to every instance
- **Reconciliation job** as a safety net — detects and auto-corrects drift (e.g. after downtime), and logs every correction so nothing happens silently
- **Aggregated query log** across all instances, so you can whitelist a blocked domain no matter which instance saw it
- **Dynamic instance management** — add, remove, or disable AdGuard instances from the UI, no config file edits
- **Notifications** via configurable webhooks to Home Assistant, Discord, or Gotify

## Architecture

```
┌─────────────┐        push         ┌──────────────────┐
│             │ ──────────────────► │  AdGuard Home #1  │
│ AdGuardHub  │                     └──────────────────┘
│  (source of │        push         ┌──────────────────┐
│   truth)    │ ──────────────────► │  AdGuard Home #2  │
│             │                     └──────────────────┘
└─────────────┘
      ▲
      │ reconcile (drift detection)
      └──────────────────────────────────────────────────
```

## Tech stack

- **Backend:** Python / FastAPI
- **Frontend:** React / TypeScript
- **Storage:** SQLite
- **Deployment:** single Docker container

## Status

🚧 In active design/development. AdGuard Home support first; Pi-hole support is planned via an adapter layer once the core is stable.

## License

MIT
