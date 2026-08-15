# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All backend commands assume `cd backend` with the venv activated (`venv\Scripts\activate` on Windows).

```bash
# First-time backend setup
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium     # required for the screenshot endpoint

# Run (both processes, from repo root)
start.bat                                  # backend + frontend + opens browser

# Run backend alone — keep the host at 127.0.0.1 (see "No authentication" below)
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Run frontend alone
cd frontend && npm install && npm run dev   # http://localhost:5173
cd frontend && npm run build                # production build; catches unused/broken imports
```

### Database migrations

Alembic runs automatically on app startup via `db_migrate.run_migrations()` in `main.py` — there is no separate migrate step in normal use. Manual operations:

```bash
alembic upgrade head                              # apply pending migrations
alembic revision --autogenerate -m "description"  # after changing models.py
alembic downgrade -1
```

Migrations must be written **idempotently** (inspect `sa.inspect(op.get_bind()).get_table_names()` before creating/dropping) because existing installs may carry databases built by the pre-Alembic `create_all()` path. `render_as_batch=True` is set in `migrations/env.py` — required for SQLite `ALTER TABLE`.

### Tests

There is no test suite (no pytest, no vitest). Verify changes by running the app and exercising the affected endpoint or tab. `npm run build` is the closest thing to a frontend check.

## Architecture

Two local processes. Vite (5173) proxies `/api` → FastAPI (8000) with `ws: true`, so HTTP **and** WebSockets share one origin in dev. Frontend code must therefore use relative paths (`/api/...`) and derive WebSocket URLs from `window.location` — hardcoding `localhost:8000` breaks the panel for anyone not on the serving machine.

### No authentication — this is load-bearing

Nothing in the API is authenticated. The SSH and RDP WebSocket endpoints will proxy a connection to any host for anyone who can reach them, so binding to `127.0.0.1` is the security boundary, not a preference. Do not change the host in `start.bat` / `start-backend.bat` / README without adding auth first.

### Backend: one router per tool

`backend/routers/*.py` are self-contained — each defines its own Pydantic request/response models inline rather than sharing a central `schemas.py`. Adding a tool means: new router file + one `include_router()` line in `main.py`. Shared pieces are deliberately few:

- `quick_check.validate_domain()` — the SSRF/format guard. `screenshot.py` imports it; any new endpoint that accepts a user-supplied hostname should too.
- `rate_limiter.limiter` — slowapi. Apply as `@router.get(...)` then `@limiter.limit("N/minute")` (limiter must be the *inner* decorator), and the endpoint function **must** take `request: Request` or slowapi raises at runtime.
- `error_analysis.ERROR_DB` — HTTP status → cause list, technician steps, and a customer-facing Turkish draft. Consumed by `quick_check` to enrich failing checks.

**Blocking I/O must go through `run_in_executor`.** DNS (dnspython), raw WHOIS over port 43, synchronous SSL handshakes, and Playwright are all blocking; every call site wraps them and adds an `asyncio.wait_for` timeout. Playwright additionally uses its own `ThreadPoolExecutor` because `sync_playwright` needs a thread with no running event loop.

### Credential handling on the terminal endpoints

Neither SSH nor RDP credentials may appear in a URL — URLs land in browser history, proxy logs, and uvicorn's access log.

- **SSH** (`routers/ssh.py`): the browser opens the socket, then sends host/username/password as the **first JSON message**. Subsequent frames are raw terminal bytes, except JSON `{type: "resize"}` control messages.
- **RDP** (`routers/rdp.py`): credentials go to `POST /api/rdp/session` in the body; it returns a 60-second, **single-use ticket** held in an in-process dict. The WebSocket carries only `?ticket=`. `_redeem_ticket()` pops the entry, so a replayed ticket fails. Because the store is in-process, this does not survive a reload mid-connect and will not work across multiple workers.

RDP also requires `guacd` reachable at `127.0.0.1:4822` (`docker run -d -p 4822:4822 guacamole/guacd`); `rdp.py` speaks the Guacamole wire protocol directly (`LEN.VALUE,...;` instructions) and hands frames to `guacamole-common-js` in the browser.

### Frontend: no router

`App.jsx` holds a `view` string in `useState` and switches on it; `Sidebar.jsx` holds the `navItems` array that sets it. There is no react-router. Adding a tab = new component + one `navItems` entry + one `case` in the switch. Components fetch with bare `axios` (no shared API client) and own their loading/error state.

### Styling

Two layers, both in play at once:

1. **Design tokens** in `tailwind.config.js` — Material-style names (`surface-*`, `on-surface-*`, `primary-*`, `outline-*`) plus a typographic scale (`text-body-md`, `text-label-sm`, `text-title-md`, `text-display-md`) and `rounded-btn` / `rounded-card`.
2. **Component classes** in `src/index.css` under `@layer components` — `.card`, `.btn-primary`, `.input-field`, `.textarea-field`, `.nav-item`, `.status-dot-{healthy,warning,error}`, `.badge-*`, `.log-stream`, `.glass-panel`.

Existing components mix these with inline `style={{ color: '#1a1d2e' }}` hex literals. Match the surrounding file rather than normalizing.

`DESIGN.md` describes a **dark** "Atmospheric Precision" theme that no longer matches the app — the UI switched to a light theme (`#f0f2f7` background) in commit `d486253` and the document was never updated. Treat `index.css` and `tailwind.config.js` as the source of truth for visual decisions.

### Data

`models.py` contains only `HazirYanit` and `HazirYanitKategori`; the ticket/AI modules were removed. On the first `GET /api/hazir-yanitlar` with an empty table, `seed_if_empty()` loads `backend/data/hazirYanitlar.json` (89 entries). The backend must not read from `frontend/` — that coupling was removed deliberately so the backend can be deployed alone.

In `hazir_yanitlar.py`, the `/kategoriler` routes are declared **before** `/{yanit_id}`; reordering them makes FastAPI match `kategoriler` as an int path param and break the category endpoints.

## Conventions

- **All user-facing strings, comments, and commit messages are Turkish.** API error `detail` values are shown directly in the UI, so write them for the support technician reading the screen.
- DNS queries bypass the system resolver and go to public resolvers (`8.8.8.8`, `1.1.1.1`, `9.9.9.9`) with explicit timeouts — the panel is used to diagnose DNS, so it must not inherit the local machine's cache or resolver.
- Check results use a four-state vocabulary — `healthy` / `warning` / `error` / `info` — that maps to the `.status-dot-*` classes. `quick_check` deliberately downgrades DNS `error` → `warning` when HTTP and SSL both succeed, since the site is demonstrably reachable.
