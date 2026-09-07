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
  (write surface via the `decide` stage), `/debug/ingest` (full-batch ingest),
  `/debug/logs`, `/debug/wipe` (two-layer-verified DB wipe), `/debug/stale`
  (removed-at-source events), `/debug/tests` (run the pytest suite). Loopback-only;
  inside Docker it auto-binds `0.0.0.0` and accepts the Docker bridge subnet
  (see gotchas).

## Architecture

Data flows: **gatherer (gather) → sieve (sort) → decisionmaker (decide) → DB**.

```
config.yaml → Settings → registry.load_sources()
  → ingest.run() → gatherer.run(source)     # GathererResult (ScrapedEvent[])
  → sieve.classify()                       # SieveResult (new/updated/unchanged)
  → decisionmaker.apply()                  # Event rows upserted
  → SQLite (data/ripcale.db, WAL)
```

The Gatherer→Sieve→Decisionmaker data contract is specified in
`docs/GATHERER_CONTRACT.md`.

Key files:

- `app/config.py` — `Settings` (config.yaml + .env; env > dotenv > yaml > defaults).
- `app/logging.py` — `setup_logging()` (console + rotating `data/ripcale.log`, idempotent) + `read_log_tail()` (constant-time backward tail for `/debug/logs`).
- `app/models.py` — `Source`, `Event` (SQLModel).
- `app/db.py` — `engine`, `init_db()`, `wipe_db()` (delete Event→Source, schema intact), WAL + foreign-key pragmas.
- `app/schema.py` — pipeline contracts (`SourceConfig`, `ScrapedEvent`,
  `ImageRef`, `GathererResult`, `ClassifiedEvent`, `SieveResult`) + `dump_images()`/`load_images()`.
- `app/identity.py` — `stable_id()`, `content_hash()`.
- `app/timeutil.py` — `to_utc_naive()`, `parse_iso_utc()`.
- `app/registry.py` — `load_sources()`, `load_gatherer()`.
- `app/gatherers/<name>/gatherer.py` — each gatherer exposes `run(source)`.
- `app/sieve/` — `classify()` re-exported from `sieve.py` (change detection; `_relevance()` is a
  pass-through placeholder for future drop-past rules).
- `app/decisionmaker/` — `apply()` re-exported from `decisionmaker.py` (persist; stub for future cross-source heuristics).
- `app/ingest.py` — `run()` / `run_report()` / `process_source()` orchestrator (CLI + debug ingest page share `_run()`).
- `app/serializers.py` — `Event` → FullCalendar dict.
- `app/services/events.py` — `query_events()`, `get_event()`, `source_names()`.
- `app/services/ics.py` — `event_to_vevent()`, `events_to_ics()`.
- `app/services/stats.py` — `overview()`, `sources()`, `event_dump()`, `stale_events()`, `read_last_ingest()`.
- `app/services/status.py` — per-source run status store (`data/status.json`): `read_status()` / `record_status()` / `record_run()` / `reset_status()` + `source_status()` / `gatherer_rollup()`.
- `app/services/wipe.py` — `wipe_all()` (DB wipe + reset status/last-ingest).
- `app/services/testrunner.py` — `collect_tests()` / `run_tests()` (subprocess `python -m pytest`).
- `app/security.py` — `in_docker()`, `is_debug_allowed()`, CSRF, `form_data()`.
- `app/web.py` — HTML helpers (dashboard + playground pages).
- `app/routers/{events,feeds,debug,pipeline,ingest,wipe,tests}.py` — HTTP handlers.
- `app/public.py`, `app/admin.py` — the two listeners.
- `app/main.py` — local-dev launcher (spawns both; Docker runs the two directly).

## Run / test / ingest

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest                       # test suite (89)
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
- **Recurrence** — `Event.rrule` holds an RFC 5545 RRULE (the series master;
  interpreted relative to `start_at` in `timezone`). `recurrence_id` / `exdates`
  (per-occurrence overrides/deletions, wired in F31.02 — an override's id is
  `sha256(source+uid+recurrence_id)`) and `redirect_to_id` (event
  redirects/symlinks, groundwork) live on `Event`.
- **Event listing is future-first, capped by default** — `query_events()` orders by
  `start_at` descending (furthest future first; NULL start sorts last) and caps at
  `DEFAULT_LIMIT` (500) unless a `?limit=` is passed (`None`/`0` = unbounded, used
  by the ICS feed). The default lives in one place: `app/services/events.py`.
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
- **Gatherer errors are caught, not fatal** — `ingest.run()` logs each failed
  source (with a rollback) and continues; the pipeline playground returns a
  clear error page. Logging is via `logging.getLogger(__name__)` (configured by
  `setup_logging()`).
- **Run status is agnostic** — every source run (batch ingest *and* the pipeline
  playground) records its outcome to `data/status.json` (`ok`/`warning`/`error`);
  `/debug` derives 🟢/🟡/🔴/⚪ lights from it, rolled up per gatherer by highest
  severity.
- **Logs are a shared rotating file** — `setup_logging()` attaches a
  `RotatingFileHandler` to the root logger in every entrypoint, so `public`,
  `admin`, and `ingest` all write the same `{data_dir}/ripcale.log`. Rotation is
  *not* multi-process-safe (a rare race if two processes hit `log_max_bytes`
  simultaneously); disk stays capped at ~`log_max_bytes * (log_backup_count + 1)`.
- **Wipe is schema-preserving** — `wipe_db()` deletes Event→Source rows only and
  `wipe_all()` also resets `data/status.json` + `data/last_ingest.json`; the
  tables survive so the server keeps serving and a later ingest repopulates.
- **`/debug/tests` runs pytest out-of-process** — `app/services/testrunner.py`
  shells out to `python -m pytest` (same as the CLI), isolated from the server.
  The Docker image installs the `[dev]` extras and ships `tests/` so this works
  in-container too.
- **Stale/removal detection (F15)** — `Event.last_seen_at` is stamped with the
  source's run timestamp on every seen event during `apply()` (new/updated/
  unchanged), and `source.last_fetched_at` is set to the same `run_ts`. An event
  is "removed at the source" when `last_seen_at != source.last_fetched_at` (or is
  NULL). `apply()` reports a `removed` count; `stats.stale_events()` / `/debug/stale`
  list them. Detection only — stale events are still served by `/events` until
  F22 archives them.

## Configuration

Fields in `config.yaml` (env prefix `RIPCALE_`; `.env` overrides):

- `public_host` / `public_port` — read-only listener (default `0.0.0.0` / `8081`).
- `admin_host` / `admin_port` — debug listener (default `127.0.0.1` / `8082`).
- `data_dir` — SQLite + `last_ingest.json` location (default `data`).
- `database_url` — optional override (defaults to `sqlite:///{data_dir}/ripcale.db`).
- `log_file` — rotating log path (relative → `data_dir`; empty → `data/ripcale.log`).
- `log_max_bytes` — rotate once the file reaches this size (default `1000000`).
- `log_backup_count` — rotated backups to keep (default `3`).
- `cors_origins` — CORS origin list (default `*`).
- `debug_allowed_cidrs` — extra IPv4 CIDRs for the admin endpoints (loopback always allowed).
- `debug_token` — optional fixed CSRF token (auto-generated if empty).
- `gatherers` — per-gatherer defaults, e.g. `{elfsight: {priority: 5}}` (extensible).
- `sources` — list of `{name, gatherer, url, is_public, priority, default_categories}`; an optional source `priority` overrides the gatherer default (fallback 0).

## Maintenance (do this on every change)

- Move the relevant card in `TODO.md` (Backlog → In Progress → Done) as work progresses.
- Add a dated `DEVLOG.md` entry per change (tag AI-authored entries with `[AI]`).
- Update this file whenever architecture, configuration, or invariants change.

The original project vision lives in the repo-root `DEVLOG.md`; the ongoing
development journal is `DEVLOG.md` in this directory.
