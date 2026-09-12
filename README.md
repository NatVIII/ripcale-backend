# ripcale

Calendar aggregator backend powering rva.rip.

## Run

ripcale is split into two listeners:

- **public** (read-only API) on `:8081`
- **admin** (debug + pipeline playground + JSON admin API) on `127.0.0.1:8082`
  — the interactive surface requires a session login (see "Admin login" below).

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m app.main   # dev launcher — runs both public + admin
```

Or run them separately:

```sh
.venv/bin/python -m app.public   # :8081
.venv/bin/python -m app.admin    # 127.0.0.1:8082
```

`GET :8081/healthz` returns `{"status":"ok","service":"ripcale","version":"0.1.0"}`.

## Docker

```sh
docker compose up --build
```

Starts two services: `public` (`0.0.0.0:8081`) and `admin` (`127.0.0.1:8082`,
loopback-only so the interactive surface isn't reachable over the network).

## Configuration

Configuration is split in two:

- **`config.yaml`** — system settings (hosts/ports, logging, debug access). Hand-edited.
- **`intake.yaml`** — intake data (sources, per-gatherer defaults, category
  symlinks). Hand-editable *and* written by the program (via the admin menu).

Both are gitignored; `config.example.yaml` and `intake.example.yaml` are the
tracked templates. `intake.example.yaml` ships one real *public* source (Studio
Two Three) as starter data. API keys and secrets go in `.env` (see
`.env.example`), never in `config.yaml`. Env vars / `.env` override `config.yaml`.

The admin login is configured via `.env` too: `RIPCALE_ADMIN_USERNAME`,
`RIPCALE_ADMIN_PASSWORD_HASH`, and `RIPCALE_PEPPER`. (API tokens are per-user,
minted in the DB with `app.auth token create`, not an env var.)

`./data/` holds only generated data (the SQLite DB, logs, status) and is safe to wipe.

## Admin login

The admin app requires a session login. One-time setup:

```sh
.venv/bin/python -m app.auth gen-pepper           # → put in .env as RIPCALE_PEPPER
.venv/bin/python -m app.auth hash-password        # → put in .env as RIPCALE_ADMIN_PASSWORD_HASH
.venv/bin/python -m app.admin                     # bootstrap creates the admin user
```

Then open `http://127.0.0.1:8082/debug/login` and sign in. For bots/automation,
mint a per-user API token (shown once — save it) and send it as
`Authorization: Bearer <token>`:

```sh
.venv/bin/python -m app.auth token create admin --label my-bot
```

Two gotchas:

- **Set the pepper before hashing** — the hash bakes the pepper in, so generate
  `RIPCALE_PEPPER` first, then `RIPCALE_ADMIN_PASSWORD_HASH`.
- **To change a password later, use `app.auth change-password admin`** — editing
  `RIPCALE_ADMIN_PASSWORD_HASH` only seeds the admin *if it doesn't exist yet*;
  it won't update an existing user.

## Command reference

Every entrypoint, with its intended use. (Run from the repo root inside the venv.)

### Servers

```sh
.venv/bin/python -m app.public   # read-only API on :8081
.venv/bin/python -m app.admin    # debug/admin on 127.0.0.1:8082 (session login required)
.venv/bin/python -m app.main     # dev launcher — runs both (not used in Docker)
```

### Ingest

```sh
.venv/bin/python -m app.ingest --dry-run   # classify only, no writes (preview)
.venv/bin/python -m app.ingest             # scrape → sieve → decide → store
.venv/bin/python -m app.gatherers.elfsight # run one gatherer standalone (dev)
```

### Inspect data (reads the DB directly; no IP gate applies)

```sh
.venv/bin/python -m app.debug                     # overview stats (default)
.venv/bin/python -m app.debug stats               # same as above
.venv/bin/python -m app.debug sources             # per-source summary
.venv/bin/python -m app.debug events --id <id>    # dump a single event
```

### Authentication / users

```sh
.venv/bin/python -m app.auth hash-password          # prompt → print an argon2id hash (for .env)
.venv/bin/python -m app.auth gen-pepper             # print a random pepper (for .env)
.venv/bin/python -m app.auth add-user <username>    # create a user (prompts for a password)
.venv/bin/python -m app.auth change-password <username>
.venv/bin/python -m app.auth remove-user <username>
.venv/bin/python -m app.auth list-users
.venv/bin/python -m app.auth token create <username> [--label <label>]   # mint an API token (shown once)
.venv/bin/python -m app.auth token list <username>                        # list a user's tokens (hashes only)
.venv/bin/python -m app.auth token revoke <token>                         # revoke a token
```

### Dev / Docker

```sh
.venv/bin/python -m pytest          # run the test suite
docker compose up --build           # public + admin services
```

## Ingest

```sh
.venv/bin/python -m app.ingest --dry-run   # classify only, no writes
.venv/bin/python -m app.ingest             # scrape -> sieve -> decide -> store
```

The pipeline is gather (gatherer) -> sieve (read-only new/updated/unchanged
diff against the DB) -> decisionmaker (persist). A gatherer can be run standalone:

```sh
.venv/bin/python -m app.gatherers.elfsight
```

## API

Events are served in FullCalendar's `event-parsing` format (`id`, `title`,
`start`, `end`, `allDay`, `url`, `extendedProps` for description/location/
categories/images/timezone/source).

Categories are `class:name` identities. Only the **"true"** categories (classes
listed in `intake.yaml`'s `exposed_classes`, default `external`) are exposed by
`/events`, `/feed.ics`, and `/api/v1/events`; internal `intake:*` categories (and
anything else) stay in the DB for data integrity but are hidden from the public
read path.

| Endpoint | Description |
|---|---|
| `GET /events?start=&end=&category=&limit=` | list events (ISO range + tag filter) |
| `GET /events/{id}` | single event (404 if absent) |
| `GET /feed.ics?tag=` | full ICS feed (subscribe; optionally filtered by tag) |
| `GET /events/{id}/ics` | single event ICS (404 if absent) |
| `GET /healthz` | liveness |

## Admin API (`/api/v1/*`)

A versioned JSON admin API on the **admin** app (`127.0.0.1:8082`), for bots and
automation. Every response is a `{ok, data|error}` envelope; authenticate with a
per-user API token (`Authorization: Bearer <token>` — mint one with
`python -m app.auth token create <username>`), or with a session cookie from the
login. Writes default to dry-run where applicable.

**Read**

| Endpoint | Description |
|---|---|
| `GET /api/v1/stats` | overview counts + last ingest |
| `GET /api/v1/sources` | source list |
| `GET /api/v1/status` | per-source run status + gatherer rollup |
| `GET /api/v1/events?start=&end=&category=&limit=` | events (FullCalendar) |
| `GET /api/v1/events/{id}` | single event |
| `GET /api/v1/stale` | removed-at-source events |
| `GET /api/v1/coherence` | config/intake coherence issues |
| `GET /api/v1/logs?n=` | last N log lines |
| `GET /api/v1/tests` | list collected tests |

**Write**

| Endpoint | Description |
|---|---|
| `POST /api/v1/ingest` `{dry_run}` | run the full batch ingest |
| `POST /api/v1/retag` `{from, to?, dry_run?}` | mass category rename/remove |
| `POST /api/v1/wipe/begin` → `POST /api/v1/wipe/confirm` `{challenge}` | challenge-response DB wipe |
| `POST /api/v1/tests` `{test?}` | run the suite (or one test) |
| `POST /api/v1/pipeline/gather` `{source…}` | run a gatherer |
| `POST /api/v1/pipeline/sieve` `{source…}` | run + diff vs DB |
| `POST /api/v1/pipeline/decide` `{source…, dry_run?}` | run + diff + persist |
| `POST /api/v1/pipeline/categorize` `{source…, rules?, include_configured?, dry_run?}` | apply custom category rules |
| `POST /api/v1/auth/login` `{username, password}` | issue a session (also sets a cookie) |
| `POST /api/v1/auth/logout` | destroy the session |

## Debug & pipeline playground

Served by the **admin** app on `127.0.0.1:8082`. Inspect the stored data and
drive each pipeline stage from the browser (log in at `/debug/login` first).

- `GET /debug` — static overview dashboard (counts, categories, sources, last ingest).
- `GET /debug/pipeline` — home page linking to the stage pages:
  - **gather** — run a gatherer, see the full `GathererResult`.
  - **categorize** — apply custom category rules, see the resulting tags.
  - **sieve** — run a gatherer + diff vs the DB (no writes).
  - **decide** — run + diff + persist (writes).
- `GET /debug/ingest` — run the full batch ingest (dry-run by default).
- `GET /debug/logs` — tail the log file.
- `GET /debug/stale` — list removed-at-source events.
- `GET /debug/retag` — mass category rename/remove.
- `GET /debug/wipe` — challenge-response database wipe.
- `GET /debug/tests` — run the pytest suite.
- CLI equivalent: `python -m app.debug [stats|sources|events --id <id>]`.

### Access control

The admin app binds to loopback (`127.0.0.1`) by default, so it's unreachable
from the network. Inside Docker it instead binds `0.0.0.0` (required for the
published port) and auto-accepts the Docker bridge subnet (`172.16.0.0/12`) —
the host publish `127.0.0.1:8082:8082` still keeps it loopback-only from the
outside. If you ever widen the bind, the IP allowlist applies: loopback is
always allowed, other hosts must fall within `debug_allowed_cidrs`.

The `/debug` dashboard and `/api/v1/*` additionally require authentication:

- **Browser** — log in at `/debug/login`; the session cookie gates `/debug`.
- **API** — send `Authorization: Bearer <per-user token>` to `/api/v1/*`
  (a session cookie also works — one unified auth check).
- **CSRF** — the pipeline playground embeds a CSRF token in its forms (set a
  fixed one via `RIPCALE_DEBUG_TOKEN`, or it's auto-generated).

After a real ingest run, the report is written to `data/last_ingest.json` and
shown on the dashboard.
