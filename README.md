# ripcale

Calendar aggregator backend powering rva.rip.

## Run

ripcale is split into two listeners:

- **public** (read-only API) on `:8081`
- **admin** (debug + pipeline playground) on `127.0.0.1:8082`

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

Configuration lives in `config.yaml` (gitignored — source URLs are secret);
copy `config.example.yaml` to `config.yaml` and adjust. API keys and secrets go
in `.env` (see `.env.example`), never in `config.yaml`. Env vars / `.env`
override `config.yaml`.

`./data/` holds only generated data (the SQLite DB) and is safe to wipe.

## Ingest

```sh
.venv/bin/python -m app.ingest --dry-run   # classify only, no writes
.venv/bin/python -m app.ingest             # scrape -> sieve -> decide -> store
```

The pipeline is gather (source module) -> sieve (read-only new/updated/unchanged
diff against the DB) -> decisionmaker (persist). A module can be run standalone:

```sh
.venv/bin/python -m app.sources.elfsight
```

## API

Events are served in FullCalendar's `event-parsing` format (`id`, `title`,
`start`, `end`, `allDay`, `url`, `extendedProps` for description/location/
categories/images/timezone/source).

| Endpoint | Description |
|---|---|
| `GET /events?start=&end=&category=&limit=` | list events (ISO range + tag filter) |
| `GET /events/{id}` | single event (404 if absent) |
| `GET /feed.ics?tag=` | full ICS feed (subscribe; optionally filtered by tag) |
| `GET /events/{id}/ics` | single event ICS (404 if absent) |
| `GET /healthz` | liveness |

## Debug & pipeline playground

Served by the **admin** app on `127.0.0.1:8082`. Inspect the stored data and
drive each pipeline stage from the browser.

- `GET /debug` — static overview dashboard (counts, categories, sources, last ingest).
- `GET /debug/pipeline` — home page linking to the three stage pages:
  - **gather** — run a module, see the full `ModuleResult`.
  - **sieve** — run a module + diff vs the DB (no writes).
  - **decide** — run + diff + persist (writes).
- CLI equivalent: `python -m app.debug [stats|sources|events --id <id>]`.

### Access control

The admin app binds to loopback (`127.0.0.1`) by default, so it's unreachable
from the network. Inside Docker it instead binds `0.0.0.0` (required for the
published port) and auto-accepts the Docker bridge subnet (`172.16.0.0/12`) —
the host publish `127.0.0.1:8082:8082` still keeps it loopback-only from the
outside. If you ever widen the bind, the IP allowlist applies: loopback is
always allowed, other hosts must fall within `debug_allowed_cidrs`. The pipeline
playground additionally requires a CSRF token (embedded in its forms; set a
fixed one via `RIPCALE_DEBUG_TOKEN`, or it's auto-generated).

After a real ingest run, the report is written to `data/last_ingest.json` and
shown on the dashboard.
