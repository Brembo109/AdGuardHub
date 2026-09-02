# AdGuard-compatible API

Apps and integrations built for AdGuard Home speak `/control/*`. AdGuardHub serves that
surface too, so you can point an existing client — an iOS/Android remote, a script, a Home
Assistant integration — at the hub instead of at one node:

- **configuration reads** come from the hub's own state, so what a client sees is what the
  hub enforces;
- **writes go through the hub**: a rule added from your phone lands in the central model,
  is pushed to every instance, and shows up in the history like any other change;
- **statistics** are summed across the instances (with the average response time weighted by
  query count, not naively averaged), and the query log is the aggregated one, with the
  answering node in each entry's `client_info`.

Sign in with the AdGuardHub admin account — the same credentials as the web UI. Both ways in
that AdGuard Home offers work: HTTP Basic Auth on any `/control/*` request, which is what the
phone remotes and the Home Assistant integration send, or a `POST /control/login` followed by
the session cookie. The surface can be switched off under *Settings → Sync & timers*.

```bash
curl -u admin:yourpassword http://adguardhub.lan/control/status
```

Basic Auth is accepted only on `/control/*`; the hub's own `/api/*` stays cookie-only. Since
the password arrives on every request, it is worth remembering that this travels in the clear
over plain HTTP — the same reason the hub belongs on the LAN or behind a VPN rather than on the
open internet.

Two honest limits: DHCP is not offered (the hub never manages it), and `filtering/refresh` is
a no-op because the hub tracks subscription URLs rather than their contents.
