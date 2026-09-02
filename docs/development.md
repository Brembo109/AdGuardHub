# Development

Backend:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ADGUARDHUB_DATA_DIR=./data uvicorn app.main:app --reload
```

Frontend (proxies `/api` to `127.0.0.1:8000`):

```bash
cd frontend
npm install
npm run dev
```

Local development stays on uvicorn's default port 8000 — binding 80 on a host needs root.
Only the container listens on 80.

Checks — the same ones CI runs:

```bash
cd backend && ruff check . && pytest
cd frontend && npm run lint && npm test && npm run i18n:check && npm run build
```

In production the backend serves the built frontend from `ADGUARDHUB_STATIC_DIR`, so the whole
thing is one container and one port.

## Tests

The backend is covered by pytest, driven through the API against an in-memory adapter double
rather than a real AdGuard instance. `npm test` runs the frontend's, on Vitest with jsdom;
`npm run test:watch` reruns them as you edit.

The frontend suite is deliberately narrow. It covers the logic that has no other safety net and
that has actually gone wrong: the locale the formatters follow, placeholder interpolation, the
language a first-time visitor gets (including a private window where `localStorage` throws), and
the two hand-drawn charts, whose axis rounding and text fitting were arrived at by measuring
rendered strings. Pages and the API client are not covered — they are mostly plumbing, and the
end-to-end behaviour they carry is already exercised by the backend suite.

One convention worth knowing: a chart label is asserted **in German**. In English a bare
`{n} queries` and a translated `t('{count} queries')` render identical text, so an English
assertion would pass either way and pin nothing.

## Translations

Translations are keyed on the English source text, so a call site reads as prose and a missing
translation falls back to a correct English sentence rather than to a key name. The cost is that
editing an English string silently unhooks its German, so `npm run i18n:check` walks every
`t('…')` call site and fails on anything missing from `src/i18n/de.ts` — or still in it but no
longer used. Strings that reach `t()` through a variable are listed in `src/i18n/dynamic-keys.json`;
for the ones the backend serves (section titles, field labels and help text in
`backend/app/adapters/sections.py`) a backend test keeps that list in sync.

Adding a language means a dictionary next to `de.ts`, an entry in `DICTS` and `LANGUAGES`, and
extending the check to cover it.

## Project layout

```
adguardhub/
├── backend/
│   ├── app/
│   │   ├── adapters/     # DnsAdapter interface + AdGuard Home implementation
│   │   ├── api/          # FastAPI routers
│   │   ├── services/     # sync, reconcile, querylog, notify, importer
│   │   ├── models.py     # SQLAlchemy models (the central state)
│   │   └── main.py
│   └── tests/
├── frontend/             # React + TypeScript (Vite)
│   ├── src/i18n/         # English-keyed dictionaries + the completeness check
│   └── scripts/
├── docs/                 # This documentation, and the screenshots
├── packaging/            # systemd unit template for the native install
├── .github/workflows/    # ci.yml, docker-publish.yml
├── Dockerfile
├── docker-compose.yml
└── install.sh            # Native installer (Debian/Ubuntu + systemd)
```
