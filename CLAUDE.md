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

Backend has a pytest suite under `backend/tests/`. There is still no frontend
test runner — `npm run build` remains the closest thing to a frontend check.

```bash
cd backend
venv/bin/pip install -r requirements-dev.txt   # pytest; ÜRETİME kurulmaz
venv/bin/python -m pytest                       # tümü
venv/bin/python -m pytest -m "not network"      # ağsız (CI)
```

Kapsam bilinçli olarak dar: **sessizce yanlış cevap üretebilecek** yerler.
SSRF kapısı ve girdi doğrulama (`test_guvenlik_kapilari.py`), zincir motorunun
saf mantığı — joker eşleşmesi, SC-081v3 geçerlilik takvimi, yol kurma, güven
depolarının tutarlılığı (`test_ssl_chain_core.py`) ve Hızlı Kontrol'ün SSL
teşhisi (`test_quick_check_ssl.py`).

Üyelik iki dosya ekledi ve ikisi de **kapı** testidir — "doğru kullanıcı
yapabiliyor mu"dan çok "yanlış kullanıcı yapamıyor mu": alan adı kapısı,
doğrulama, oturum ömrü, CSRF, kaba kuvvet (`test_uyelik.py`) ve üç katmanlı
yetki ayrımı — anonim / üye / yönetici (`test_yetki.py`). `conftest.py` süiti
geçici bir veritabanına yönlendirir ve rate limiti kapatır; limitin kendisi
`test_ip_rate_limit_acikken_calisir` içinde bilerek geri açılır.

İki kural:

- **`conftest.py` rate limit'i kapatır.** Uçlar 10-20/dakika sınırlı; onlarca
  doğrulama testi aynı istemciden gelince 400 yerine 429 görülüyor ve test
  gerçek davranışı değil kendi kurgusunu ölçüyor. Sınırın kendisi
  `test_rate_limit_calisiyor` içinde bilerek açılarak doğrulanır.
- **Ağ gerektiren testler `@pytest.mark.network` ile işaretlenir.** Geri kalanı
  tamamen ağsız çalışır; TLS el sıkışmaları sentetik sertifikalarla ve
  monkeypatch ile taklit edilir.

## Architecture

Two local processes. Vite (5173) proxies `/api` → FastAPI (8000) with `ws: true`, so HTTP **and** WebSockets share one origin in dev. Frontend code must therefore use relative paths (`/api/...`) and derive WebSocket URLs from `window.location` — hardcoding `localhost:8000` breaks the panel for anyone not on the serving machine.

### Three access tiers — know which one an endpoint is in

Since 31 Aug 2026 the panel has **application-level membership**, but it covers
only part of the surface. Adding an endpoint means deciding which tier it joins:

| Tier | Endpoints | Enforced by |
|---|---|---|
| **Open** | DNS, SSL, quick-check, screenshot, blacklist, mail-health, IP, site-speed, `/api/uyelik/*` | nothing |
| **Membership** | `/api/hazir-yanitlar` (read = member, write = admin), `/api/yonetim/*` (admin) | `auth_core` dependencies, **in the app** |
| **Nginx Basic Auth** | `/api/admin`, `/api/ssh`, `/api/rdp`, `/api/ftp` | reverse proxy, ambient credentials |

The SSH and RDP WebSocket endpoints still proxy a connection to any host for
anyone who gets past Basic Auth, so binding to `127.0.0.1` behind the reverse
proxy remains the boundary for those. Do not expose the backend directly.

**Membership rules that are load-bearing** (see `deploy/UYELIK.md`,
`sast/uyelik-results.md`):

- `auth_core.alan_kontrol()` is an **exact** domain match, never a suffix match —
  suffix matching would admit `natro.com.evil.net`. Emails are ASCII-only, which
  is what stops the Cyrillic `nаtro.com` homograph.
- Sessions are **server-side rows**, not JWTs, so suspending an account kills its
  open sessions on the next request.
- Cookies carry the **`__Host-` prefix in production**. Sibling vhosts on this box
  share `ornek.com`; without the prefix one of them could shadow the session
  cookie and pin a victim to the attacker's account.
- CSRF is a synchronizer token: the `X-CSRF-Token` header is compared against
  `oturumlar.csrf` **in the database**, never against the cookie. The check lives
  in `mevcut_kullanici` so a new state-changing endpoint cannot forget it.
- bcrypt must never run on the event loop. Async endpoints use
  `asyncio.to_thread`; `_HASH_KELEPCE` caps concurrent hashes at 4. One worker
  serves SSH tunnels and Playwright too.

### Backend: one router per tool

`backend/routers/*.py` are self-contained — each defines its own Pydantic request/response models inline rather than sharing a central `schemas.py`. Adding a tool means: new router file + one `include_router()` line in `main.py`. Shared pieces are deliberately few:

- `quick_check.validate_domain()` — the **format** guard (regex, length, null byte, IP-literal rejection). It is *not* sufficient on its own: it never resolves the name, so `127.0.0.1.nip.io` and `localtest.me` pass it and point at loopback.
- `net_validation.resolve_public_ips_async()` / `assert_public_target()` — the **SSRF** guard. Any endpoint that opens an outbound connection must resolve the target through this and connect to the returned IP, not to the hostname (connecting by name lets the OS resolve a second time, reopening the DNS-rebinding window). `screenshot.py`, `quick_check.py`, `mail_health.py` and `ssl_tools.py` all go through it.
  - A target derived from a *DNS answer* (an MX host, a redirect `Location`) counts as user input — the domain owner controls it. `mail_health._smtp_banner` and `quick_check._safe_get` re-validate at those points.
  - `httpx` must run with `follow_redirects=False`; use `quick_check._safe_get`, which follows hops manually and validates each one.
  - `net_validation.make_playwright_route_guard()` — the browser-side gate. `--host-resolver-rules` only pins the *main* host; a page can reach the internal network through a redirect, iframe or subresource. `screenshot.py` and `site_speed/engine.py` both import this one function — do not fork a second copy, a patch applied to one and not the other is a silent SSRF hole.
- `rate_limiter.limiter` — slowapi. Apply as `@router.get(...)` then `@limiter.limit("N/minute")` (limiter must be the *inner* decorator), and the endpoint function **must** take `request: Request` or slowapi raises at runtime. Every endpoint that costs anything (an outbound connection, a DNS fan-out, CPU, a DB write) carries a limit; keep it that way when adding endpoints.
- `ws_utils.check_origin()` — call it **before** `websocket.accept()` on every WebSocket endpoint. WebSocket handshakes are not subject to CORS, and Basic Auth is ambient, so without this a malicious page can open a socket from the operator's browser (CSWSH).
- `error_analysis.ERROR_DB` — HTTP status → cause list, technician steps, and a customer-facing Turkish draft. Consumed by `quick_check` to enrich failing checks.

**Blocking I/O must go through `run_in_executor`.** DNS (dnspython), raw WHOIS over port 43, synchronous SSL handshakes, and Playwright are all blocking; every call site wraps them and adds an `asyncio.wait_for` timeout. Playwright additionally uses its own `ThreadPoolExecutor` because `sync_playwright` needs a thread with no running event loop.

### Credential handling on the terminal endpoints

Neither SSH nor RDP credentials may appear in a URL — URLs land in browser history, proxy logs, and uvicorn's access log.

- **SSH** (`routers/ssh.py`): the browser opens the socket, then sends host/username/password as the **first JSON message**. Subsequent frames are raw terminal bytes, except JSON `{type: "resize"}` control messages.
- **RDP** (`routers/rdp.py`): credentials go to `POST /api/rdp/session` in the body; it returns a 60-second, **single-use ticket** held in an in-process dict. The WebSocket carries only `?ticket=`. `_redeem_ticket()` pops the entry, so a replayed ticket fails. Because the store is in-process, this does not survive a reload mid-connect and will not work across multiple workers.

Both WebSocket endpoints validate `Origin` against `CORS_ORIGINS` before accepting (`ws_utils.check_origin`); a request with no `Origin` header is not from a browser and is allowed through, since the network boundary is then the only relevant control.

RDP also requires `guacd` reachable at `127.0.0.1:4822` (`docker run -d -p 4822:4822 guacamole/guacd`); `rdp.py` speaks the Guacamole wire protocol directly (`LEN.VALUE,...;` instructions) and hands frames to `guacamole-common-js` in the browser.

### Frontend: no router

`App.jsx` holds a `view` string in `useState` and switches on it; `Sidebar.jsx` holds the `navItems` array that sets it. There is no react-router. Adding a tab = new component + one `navItems` entry + one `case` in the switch. Components fetch with bare `axios` (no shared API client) and own their loading/error state.

### Styling

Two layers, both in play at once:

1. **Design tokens** in `tailwind.config.js` — Material-style names (`surface-*`, `on-surface-*`, `primary-*`, `outline-*`) plus a typographic scale (`text-body-md`, `text-label-sm`, `text-title-md`, `text-display-md`) and `rounded-btn` / `rounded-card`.
2. **Component classes** in `src/index.css` under `@layer components` — `.card`, `.btn-primary`, `.input-field`, `.textarea-field`, `.nav-item`, `.status-dot-{healthy,warning,error}`, `.badge-*`, `.log-stream`, `.glass-panel`.

Existing components mix these with inline `style={{ color: '#1a1d2e' }}` hex literals. Match the surrounding file rather than normalizing.

`DESIGN.md` describes a **dark** "Atmospheric Precision" theme that no longer matches the app — the UI switched to a light theme (`#f0f2f7` background) in commit `d486253` and the document was never updated. Treat `index.css` and `tailwind.config.js` as the source of truth for visual decisions.

### Ortam bayrağı

`os.getenv("ENV", ...)` çağrılarının varsayılanı **`production`**'dır (`main.py`
`/docs` kararı, `screenshot.py` `--no-sandbox` kararı). `.env` okunamazsa
uygulama güvenli tarafa düşmelidir; geliştirme modu açıkça seçilir.

### Site Hızı (`routers/site_speed/`)

The one tool that is a package rather than a single file, because it carries
genuinely separate concerns: `engine.py` (Playwright + CDP device/network
emulation), `timing.py` (raw asyncio DNS/TCP/TLS/TTFB phases, median of 3),
`scoring.py` (a line-for-line port of Lighthouse `getLogNormalScore` and its
curve control points), `audits.py` (our own hosting checks), `advice.py` (the
Turkish advice DB — same shape as `error_analysis.ERROR_DB`), `google.py`
(optional PSI + CrUX), `store.py` (history).

Things that will bite you here:

- **Measurement takes 20-60 s**, so the endpoint is job-based: `POST /run`
  returns an id, the UI polls `GET /job/{id}`. The job store `_ISLER` is
  in-process, like `rdp._tickets` — it does not survive a reload and needs
  the single worker.
- **The resolution gate runs in the endpoint, not the background task.**
  `validate_domain` is only a format check; `127.0.0.1.nip.io` passes it.
  Queueing first and validating later still failed safely, but wasted a queue
  slot and reported the error 15 s late.
- **Speed Index is not measured** (needs a filmstrip trace). `performance_score`
  divides by the weight of the metrics actually present, so dropping SI
  renormalises the remaining four. Say so in any UI that shows the score.
- **INP cannot be measured in a lab** — it needs real interaction. TBT is shown
  as its proxy and labelled as such; real INP only ever comes from CrUX.
- **`web-vitals` is vendored** at `site_speed/vendor/` and injected via
  `add_init_script` *before* navigation. It is not loaded from a CDN at
  runtime. Its `onLCP` silently fails to report on some pages, so
  `collector.js` also keeps a raw `largest-contentful-paint` observer and the
  engine falls back to it.
- **Emulation values come from Lighthouse's `constants.js`** (mobile: 4x CPU,
  562.5 ms latency, 1.6 Mbps; desktop: 1x CPU, 40 ms, 10 Mbps). Lighthouse
  *simulates* throttling and we *apply* it, so numbers are close but not
  identical. Changing these numbers moves every score.
- **Google is optional.** Without `PAGESPEED_API_KEY` those sections are simply
  absent. Do not try keyless PSI calls — Google bills anonymous use to a shared
  project whose daily quota is permanently 0, so every request returns 429.

### Data

`models.py` holds the response library (`HazirYanit`, `HazirYanitKategori`), the
site-speed history (`SiteHiziOlcum`) and the membership tables (`Kullanici`,
`Oturum`, `EpostaTokeni`, `DenetimKaydi`); the ticket/AI modules were removed.
`seed_if_empty()` loads `backend/data/hazirYanitlar.json` (89 entries) **at
startup** (`main._yasam_dongusu`), not on first `GET` — that endpoint now needs a
session, so seeding there would leave the table empty until someone logged in.
The backend must not read from `frontend/` — that coupling was removed
deliberately so the backend can be deployed alone.

SQLite runs in **WAL** with `foreign_keys=ON` (`database.py`). Both matter:
`delete` journal mode blocked every reader on each commit, and FK constraints are
off by default in SQLite, so `ondelete="CASCADE"` silently does nothing without
the pragma. `HOSTCHECK_DB_URL` overrides the path — `tests/conftest.py` uses it to
keep the suite out of the working database.

In `hazir_yanitlar.py`, the `/kategoriler` routes are declared **before** `/{yanit_id}`; reordering them makes FastAPI match `kategoriler` as an int path param and break the category endpoints.

## Conventions

- **All user-facing strings, comments, and commit messages are Turkish.** API error `detail` values are shown directly in the UI, so write them for the support technician reading the screen.
- DNS queries bypass the system resolver and go to public resolvers (`8.8.8.8`, `1.1.1.1`, `9.9.9.9`) with explicit timeouts — the panel is used to diagnose DNS, so it must not inherit the local machine's cache or resolver.
- Check results use a four-state vocabulary — `healthy` / `warning` / `error` / `info` — that maps to the `.status-dot-*` classes. `quick_check` deliberately downgrades DNS `error` → `warning` when HTTP and SSL both succeed, since the site is demonstrably reachable.
