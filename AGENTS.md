# AGENTS.md

Context, architecture, and operating instructions for ripcale. Read this first.

## Overview

ripcale is the calendar aggregator backend powering rva.rip. It scrapes
community event sources, normalizes them into a common schema, and exposes them
as a FullCalendar-compatible JSON API and RFC 5545 ICS feeds.

It runs as two listeners:

- **public** (`app/public.py`) — read-only API on `public_host:public_port`
  (default `0.0.0.0:8081`): `/events`, `/events/{id}`, `/feed.ics`,
  `/events/{id}/ics`, `/healthz`.
- **admin** (`app/admin.py`) — debug dashboard + pipeline playground on
  `admin_host:admin_port` (default `127.0.0.1:8082`): `/debug`, `/debug/pipeline/*`
  (the only write surface, via the `decide` stage). Loopback-only; inside Docker
  it auto-binds `0.0.0.0` and accepts the Docker bridge subnet (see gotchas).

## Architecture

Data flows: **source module (gather) → sieve (sort) → decisionmaker (decide) → DB**.

```
config.yaml → Settings → registry.load_sources()
  → ingest.run() → module.run(source)     # ModuleResult (ScrapedEvent[])
  → sieve.classify()                       # SieveResult (new/updated/unchanged)
  → decisionmaker.apply()                  # Event rows upserted
  → SQLite (data/ripcale.db, WAL)
```

The Gatherer→Sieve→Decisionmaker data contract is specified in
`docs/GATHERER_CONTRACT.md`.

Key modules:

- `app/config.py` — `Settings` (config.yaml + .env; env > dotenv > yaml > defaults).
- `app/models.py` — `Source`, `Event` (SQLModel).
- `app/db.py` — `engine`, `init_db()`, WAL + foreign-key pragmas.
- `app/schema.py` — pipeline contracts (`SourceConfig`, `ScrapedEvent`,
  `ImageRef`, `ModuleResult`, `ClassifiedEvent`, `SieveResult`) + `dump_images()`/`load_images()`.
- `app/identity.py` — `stable_id()`, `content_hash()`.
- `app/timeutil.py` — `to_utc_naive()`, `parse_iso_utc()`.
- `app/registry.py` — `load_sources()`, `load_module()`.
- `app/sources/<name>/module.py` — each source adapter exposes `run(source)`.
- `app/sieve.py` — `classify()` (change detection; `_relevance()` is a
  pass-through placeholder for future drop-past rules).
- `app/decisionmaker.py` — `apply()` (persist; stub for future cross-source heuristics).
- `app/ingest.py` — `run()` / `process_source()` orchestrator (CLI).
- `app/serializers.py` — `Event` → FullCalendar dict.
- `app/services/events.py` — `query_events()`, `get_event()`, `source_names()`.
- `app/services/ics.py` — `event_to_vevent()`, `events_to_ics()`.
- `app/services/stats.py` — `overview()`, `sources()`, `event_dump()`, `read_last_ingest()`.
- `app/security.py` — `in_docker()`, `is_debug_allowed()`, CSRF, `form_data()`.
- `app/web.py` — HTML helpers (dashboard + playground pages).
- `app/routers/{events,feeds,debug,pipeline}.py` — HTTP handlers.
- `app/public.py`, `app/admin.py` — the two listeners.
- `app/main.py` — local-dev launcher (spawns both; Docker runs the two directly).

## Run / test / ingest

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest                       # test suite (39)
.venv/bin/python -m app.main                     # dev: both listeners
.venv/bin/python -m app.public                   # :8081
.venv/bin/python -m app.admin                    # 127.0.0.1:8082
.venv/bin/python -m app.ingest --dry-run         # classify only, no writes
.venv/bin/python -m app.ingest                   # scrape -> sieve -> decide -> store
.venv/bin/python -m app.debug                    # CLI: stats / sources / events --id
docker compose up --build                        # public + admin services
```

## Invariants & gotchas

- **Naive-UTC datetimes** everywhere in storage; the original IANA zone is kept
  in `Event.timezone`. Convert with `app.timeutil.to_utc_naive()`.
- **`content_hash` is a stability contract** — defined once in `app/identity.py`;
  changing its inputs makes every stored event look "updated" on the next ingest.
- **Events carry an ordered image gallery** — `Event.images` is a JSON column of
  `{url, alt, source_url}` (`ImageRef`); the primary/cover image is `images[0]`.
- **Source URLs are never exposed by the API.** Private/secret sources live in
  `config.yaml` (gitignored); `config.example.yaml` is the tracked template and
  ships one real *public* source (Studio Two Three) as starter data.
- **Robyn router cannot express `:param.suffix`** — `/feed/:tag.ics` becomes a
  single param literally named `tag.ics`; hence `/feed.ics?tag=` and `/events/{id}/ics`.
- **Robyn leaves form bodies in `request.body`, not `request.form_data`** — use
  `app.security.form_data()` (handles both the real server and TestClient).
- **Robyn does not URL-decode `query_params`** — apply `unquote_plus` to values.
- **`icalendar` rejects unescaped newlines** in some properties (esp.
  `X-ALT-DESC`); `app/services/ics.py` sanitizes HTML newlines to spaces.
- **pydantic-settings `yaml_file` is inert unless `settings_customise_sources`
  adds `YamlConfigSettingsSource`** — already done in `app/config.py`.
- **Docker port publishing DNATs to the container's eth0** — a `127.0.0.1` bind
  is unreachable through a published port. `app/admin.py` binds `0.0.0.0` when
  `in_docker()`; the host publish `127.0.0.1:8082:8082` keeps it loopback-only.
- **Source `default_categories` are merged in the sieve** (before hashing) so
  they participate in change detection.

## Configuration

Fields in `config.yaml` (env prefix `RIPCALE_`; `.env` overrides):

- `public_host` / `public_port` — read-only listener (default `0.0.0.0` / `8081`).
- `admin_host` / `admin_port` — debug listener (default `127.0.0.1` / `8082`).
- `data_dir` — SQLite + `last_ingest.json` location (default `data`).
- `database_url` — optional override (defaults to `sqlite:///{data_dir}/ripcale.db`).
- `cors_origins` — CORS origin list (default `*`).
- `debug_allowed_cidrs` — extra IPv4 CIDRs for the admin endpoints (loopback always allowed).
- `debug_token` — optional fixed CSRF token (auto-generated if empty).
- `sources` — list of `{name, module, url, is_public, default_categories}`.

## Maintenance (do this on every change)

- Move the relevant card in `TODO.md` (Backlog → In Progress → Done) as work progresses.
- Add a dated `DEVLOG.md` entry per change (tag AI-authored entries with `[AI]`).
- Update this file whenever architecture, configuration, or invariants change.

The original project vision lives in the repo-root `DEVLOG.md`; the ongoing
development journal is `DEVLOG.md` in this directory.
