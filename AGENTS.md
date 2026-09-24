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
  `admin_host:admin_port` (default `127.0.0.1:8082`): session-authenticated
  `/debug` (login at `/debug/login`), `/debug/pipeline/*` (write surface via the
  `decide` and `categorize` stages), `/debug/ingest` (full-batch ingest),
  `/debug/logs`, `/debug/wipe` (challenge-response DB wipe), `/debug/stale`
  (removed-at-source events), `/debug/retag` (mass category rename/remove),
  `/debug/tests` (run the pytest suite), and `/api/v1/*` (the JSON admin API,
  authenticated by session cookie or a per-user API token). Loopback-only; inside
  Docker it auto-binds `0.0.0.0` and accepts the Docker bridge subnet (see gotchas).

## Architecture

Data flows: **gatherer (gather) → categorize (assign categories) → sieve (sort) → decisionmaker (decide) → DB**.

```
config.yaml → Settings (system)     intake.yaml → app/intake.py (sources/gatherers/symlinks)
  → registry.load_sources()
  → ingest.run() → gatherer.run(source)     # GathererResult (ScrapedEvent[])
  → categorize.apply(source, events)        # category rules (defaults + regex), before hash
  → sieve.classify()                       # SieveResult (new/updated/unchanged)
  → decisionmaker.apply()                  # Event rows upserted
  → SQLite (data/ripcale.db, WAL)
```

The Gatherer→Categorize→Sieve→Decisionmaker data contracts are specified in
`docs/GATHERER_CONTRACT.md`, `docs/CATEGORIZE_CONTRACT.md`,
`docs/SIEVE_CONTRACT.md`, and `docs/DECISIONMAKER_CONTRACT.md`. Contract docs are
version-stamped and test-enforced (see the "Contracts are versioned" invariant
below).

Key files:

- `app/config.py` — `Settings` (system `config.yaml` + `.env`; `config.yaml` > env > dotenv > defaults; `.env` = auth/secrets only).
- `app/intake.py` — `IntakeSettings` + `load()`/`save()` for the mutable `intake.yaml` (sources, gatherers, category symlinks).
- `app/logging.py` — `setup_logging()` (console + rotating `data/ripcale.log`, idempotent) + `read_log_tail()` (constant-time backward tail for `/debug/logs`).
- `app/models.py` — `Source`, `Event`, `User`, `LoginSession`, `ApiToken` (SQLModel).
- `app/db.py` — `engine`, `init_db()`, `wipe_db()` (delete Event→Source, schema intact), WAL + foreign-key pragmas.
- `app/schema.py` — pipeline contracts (`SourceConfig`, `ScrapedEvent`,
  `ImageRef`, `GathererResult`, `CategoryRule`, `ClassifiedEvent`, `SieveResult`) + `dump_images()`/`load_images()`.
- `app/identity.py` — `stable_id()`, `content_hash()`.
- `app/timeutil.py` — `to_utc_naive()`, `parse_iso_utc()`.
- `app/registry.py` — `load_sources()`, `load_gatherer()`.
- `app/gatherers/<name>/gatherer.py` — each gatherer exposes `run(source)`. (`elfsight` = JSON widget; `ics` = generic RFC 5545 feed, e.g. a public Google Calendar.)
- `app/categorize/` — `apply()` re-exported from `categorize.py` (config-driven category assignment, before the sieve).
- `app/sieve/` — `classify()` re-exported from `sieve.py` (change detection; fills `default_location`; `_relevance()` drops events
  outside the expiry window — F13).
- `app/decisionmaker/` — `apply()` re-exported from `decisionmaker.py` (persist; stub for future cross-source heuristics).
- `app/ingest.py` — `run()` / `run_report()` / `process_source()` orchestrator (CLI + debug ingest page share `_run()`).
- `app/serializers.py` — `Event` → FullCalendar dict.
- `app/services/events.py` — `query_events()`, `get_event()`, `set_pinned()`, `update_event()` (F28 edit), `source_names()`.
- `app/services/ics.py` — `event_to_vevent()`, `events_to_ics()`.
- `app/services/stats.py` — `overview()`, `sources()`, `event_dump()`, `stale_events()`, `read_last_ingest()`.
- `app/services/coherence.py` — `check()` (live config/intake coherence checks, fail-safe).
- `app/services/status.py` — per-source run status store (`data/status.json`): `read_status()` / `record_status()` / `record_run()` / `reset_status()` + `source_status()` / `gatherer_rollup()`.
- `app/services/wipe.py` — `wipe_all()` (DB wipe + reset status/last-ingest).
- `app/services/retag.py` — `retag()` (mass category rename/remove across all events).
- `app/services/expiry.py` — shared relevance/expiry window (`past_cutoff`/`future_cutoff`/`is_expired`/`is_relevant`; F13 sieve + F22 GC).
- `app/services/recurrence.py` — `last_occurrence()` (bounded-RRULE last instance; F12 expansion will live here).
- `app/services/archive.py` — `archive()` (soft-delete expired/removed events), `list_archived()`, `restore()` (F22).
- `app/services/scheduler.py` — background ingest scheduler (F11): `start()` (daemon thread) + `status()`.
- `app/services/lock.py` — cross-process `ingest.lock` (atomic, stale-aware) guarding `ingest._run()` (F11).
- `app/services/clock.py` — central `now()` (frozen when `debug_now` is set) + `debug_active()` (F56.01).
- `app/services/images.py` — local content-addressed image hosting (`store()`/`resolve()`/`host_images()`) + GC (`prune()`/`referenced_filenames()`) + `is_local()`/`rehost_missing_images()` (F18/F18.01).
- `app/routers/images.py` — `GET /images/{filename}` (serve hosted images; also registered on the admin app for previews).
- `app/routers/images.py` — `GET /images/{filename}` (serve hosted images).
- `app/services/actions.py` — request-agnostic admin operations (read/write/pipeline + parsing + `ActionError`); the single source of truth shared by `/api/v1/*` and the HTML debug pages. `category_mapping()` exposes the full category config + DB counts with exposure (F29).
- `app/services/testrunner.py` — `collect_tests()` / `run_tests()` (subprocess `python -m pytest`).
- `app/security.py` — `in_docker()`, `is_debug_allowed()`, CSRF, `form_data()`/`json_body()`, `api_guard()`/`session_guard()`.
- `app/services/auth.py` — argon2id password hashing, DB-backed sessions + hashed per-user API tokens, `login()` (timing-safe + rate-limited + lockout), `ensure_admin_user()`, user management + token management.
- `app/routers/auth.py` — `/api/v1/auth/login|logout` + `/debug/login`; `app/auth.py` — CLI (`hash-password`).
- `app/web.py` — HTML helpers (dashboard + playground pages).
- `app/routers/{events,feeds,debug,pipeline,ingest,wipe,tests,retag,api}.py` — HTTP handlers.
- `app/public.py`, `app/admin.py` — the two listeners.
- `app/main.py` — local-dev launcher (spawns both; Docker runs the two directly).

## Run / test / ingest

```sh
uv sync --all-extras                             # create/refresh .venv from uv.lock (incl. pytest)
.venv/bin/python -m pytest                       # test suite (338)
.venv/bin/python -m app.main                     # dev: both listeners
.venv/bin/python -m app.public                   # :8081
.venv/bin/python -m app.admin                    # 127.0.0.1:8082
.venv/bin/python -m app.ingest --dry-run         # classify only, no writes
.venv/bin/python -m app.ingest                   # scrape -> sieve -> decide -> store
.venv/bin/python -m app.debug                    # CLI: stats / sources / events --id
.venv/bin/python -m app.archive --commit          # archive (GC) — dry-run by default
.venv/bin/python -m app.images prune [--commit]   # orphan image GC — dry-run by default
.venv/bin/python -m app.audit                      # dependency vuln scan (F58.01; fails on high+)
docker compose up --build                        # public + admin services (Dockerfile runs `uv sync --frozen`)
```

Deployment is **poll-based pull** (no CI/SSH into the server): `deploy/deploy.sh`
pulls and rebuilds only when HEAD moves, driven by `deploy/ripcale-deploy.{service,timer}`;
see `docs/DEPLOYMENT.md` for the full server setup.

## Invariants & gotchas

- **Admin/debug interactivity is API-first** — every interactive/admin capability
  is exposed as a versioned JSON endpoint under `/api/v1/*` (`{ok, data|error}`
  envelope, `Authorization: Bearer <per-user API token>`, IP-gated); HTML debug pages are
  thin clients of those endpoints, never a second implementation. All real logic
  lives in `app/services/*` — specifically `app/services/actions.py`, which both
  the API router and the HTML routers call. New interactive work defaults to this.
- **Authentication (F48)** — passwords are argon2id-hashed (never plaintext) and
  stored in the `users` table; sessions are opaque in-memory tokens (24h TTL, lost
  on restart) issued over `HttpOnly`+`SameSite=Strict` cookies. Login is
  timing-safe (dummy verify for unknown users), returns a generic
  "invalid credentials" error, and is rate-limited (429 after 5 failures/5 min)
  and locked out (423 for 15 min) after 5 consecutive failures.
  Argon2 params are pinned (`ARGON2_TIME_COST`/`MEMORY_COST`/`PARALLELISM`) and
  stale hashes are transparently re-hashed on login (`check_needs_rehash`); an
  optional `pepper` (env, HMAC-keyed before hashing) adds defense-in-depth
  (changing it invalidates existing hashes — regenerate them). The `/debug`
  dashboard is session-gated (redirect to `/debug/login`); `/api/v1/*` still uses
  the `/debug` dashboard and `/api/v1/*` are both authenticated by one
  `authenticated_user()` check (a session cookie *or* a per-user API token);
  `/api/v1/*` no longer has a shared `api_token`. Admin-side only — the public API
  is unchanged.
- **Contracts are versioned + test-enforced** — each stage contract doc
  (`docs/*_CONTRACT.md`) carries a `Version: N` stamp; the stage module declares
  `CONTRACT_VERSION = N` (with a `# Contract: <stage> vN` comment);
  `tests/test_contract_*.py` (one file per stage, sharing `tests/contract_helpers.py`)
  assert they agree and that the pydantic shapes match the docs. When you change a
  contract, bump the doc version and update the code to conform (the test then
  forces the constant to follow). Gatherers are stamped **individually** — each
  `app/gatherers/<name>/gatherer.py` declares its own `CONTRACT_VERSION` (since
  gatherers are written separately); the test discovers every gatherer package
  and checks it.
- **Naive-UTC datetimes** everywhere in storage; the original IANA zone is kept
  in `Event.timezone`. Convert with `app.timeutil.to_utc_naive()`. Every datetime
  column in `app/models.py` is declared with an explicit
  `sa_column=Column(DateTime(timezone=False))` (via the `_dt()` helper) so
  SQLModel's tz-aware default can never reject our naive values (B01) — keep
  `index=True` inside `_dt(index=True)` for `Event.start_at`/`archived_at`.
- **Dependencies are locked with `uv`** — `uv.lock` is the reproducible source of
  truth (committed; the Dockerfile and `uv sync` both resolve from it). Adding or
  upgrading a dependency: edit `pyproject.toml`, run `uv lock --upgrade-package
  <name>` (or `uv lock` for a full refresh), `uv sync --all-extras`, then
  `scripts/audit.sh` (F58 vulnerability scan), `.venv/bin/python -m pytest`, and a
  `docker compose up --build` before committing. Never hand-edit `uv.lock`.
- **Dependency vulnerability scanning (F58.01)** — `osv-scanner` (copied into the
  image from `ghcr.io/google/osv-scanner`) scans `uv.lock` with the committed
  `osv-scanner.toml` ignore list and prints a **severity-sorted** report. By
  default the build **fails on un-acknowledged findings at `high`/`critical`**
  (`SCAN_FAIL_ON`, default `high`) and **fails closed on scanner errors** — the
  escape hatches are `--build-arg SCAN_FAIL_ON=""` (report only) and
  `--build-arg BUILD_DESPITE_OSV_DOWN=1` (downgrade scan errors to warnings; findings
  still gate). `app/audit.py` is the thin wrapper (`python -m app.audit`): runs
  osv-scanner, prints its report, parses the summary line, and applies the
  severity gate (`--allow-scan-errors` bypass). Local: `scripts/audit.sh`
  (docker one-liner) — informational only.
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
  `intake.yaml` (gitignored); `intake.example.yaml` is the tracked template and
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
- **Category assignment happens in the categorize stage** (`default_categories`
  is sugar for an `assign` rule, plus `sources[].rules`), and **`default_location`
  is filled in the sieve** — both before hashing, so they participate in change
  detection.
- **Category exposure is read-time, class-gated (F17)** — the DB keeps *all*
  categories (including internal `intake:*` ones) for data integrity; only the
  public read path (`/events`, `/events/{id}`, `/feed.ics`, `/api/v1/events`)
  filters them via `resolve_event_categories()`, which resolves symlinks then
  drops any category whose class isn't in `exposed_classes` (default
  `["external"]`). Admin raw views (`/debug`, `/debug/stats`,
  `/debug/events/:id`) still show everything.
- **Gatherer errors are caught, not fatal** — `ingest.run()` logs each failed
  source (with a rollback) and continues; the pipeline playground returns a
  clear error page. Logging is via `logging.getLogger(__name__)` (configured by
  `setup_logging()`).
- **Run status is agnostic** — every source run (batch ingest *and* the pipeline
  playground) records its outcome to `data/status.json` (`ok`/`warning`/`error`);
  `/debug` derives 🟢/🟡/🔴/⚪ lights from it, rolled up per gatherer by highest
  severity.
- **Scheduler + ingest lock (F11)** — the admin app runs a daemon thread that
  triggers a full ingest every `ingest_interval_minutes` (after an
  `ingest_startup_delay_minutes` cooldown). `ingest._run()` is guarded by a
  cross-process `{data_dir}/ingest.lock` (atomic `O_EXCL`, stale after one
  interval) so a scheduled run and a manual one can't overlap; on contention the
  run returns a `skipped` summary. Scheduler state (`enabled`/`interval`/
  `last_run_at`/`next_run_at`/`running`) is exposed via `GET /api/v1/scheduler`
  and a `/debug` line.
- **Central clock (F56.01)** — `app/services/clock.now()` is the single "now"
  source for domain logic (decisionmaker `run_ts`, sieve relevance, archive
  expiry, stats upcoming/past/stale). `debug_now` freezes it at a fixed instant
  for reproduction; `/events` responses carry it in the `X-Server-Time` header
  (`Access-Control-Expose-Headers` set in `app/public.py`), and `/debug` shows a
  banner when frozen. Security (auth session expiry) and audit timestamps
  (`created_at`/`updated_at`) stay on the real wall clock.
- **Image hosting (F18)** — images are hosted **pre-sieve**: `ingest.process_source`
  runs `host_images()` after `gather`, rewriting each `ImageRef.url` to a
  content-addressed local path (`/images/<sha256>.<ext>`, stored in
  `{data_dir}/images`) and stashing the origin in `source_url`. `content_hash`
  hashes images by **`url` only** (not `alt`/`source_url`), so the stable local
  URL is the change-detection identity. Served via `GET /images/{filename}` on
  the public app; ICS absolutizes local URLs with `public_base_url` (else falls
  back to `source_url`). Failed downloads leave the image on its external URL.
- **Image GC + re-host (F18.01)** — `images.prune()` deletes `{data_dir}/images/*`
  files no **live** event references (dry-run default; files referenced only by
  archived events are also removed). Surfaces: `python -m app.images prune`,
  `POST /api/v1/images/prune`, and `/debug/images`. `archive.restore()` re-hosts
  any pruned local images via `images.rehost_missing_images()` (content-addressed,
  so identical bytes re-land on the same filename) before un-archiving.
- **Archived events are frozen (F59.01)** — an incoming event whose stable id maps
  to an archived row is bucketed into `SieveResult.archived_ids` and skipped: no
  image hosting, no `content_hash` comparison, no update, no un-archive.
  `ingest.process_source` skips `host_images()` for those events; the
  decisionmaker never un-archives (archived events return only via an explicit
  `restore()`).
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
- **Relevance/expiry filter (F13)** — `sieve._relevance(events, now)` drops
  incoming events before classification (counted in `SieveResult.dropped`):
  events that fully ended more than `expire_past_days` ago, and events starting
  more than `expire_future_days` ahead. Recurring (`rrule`) series expire only
  when their **last occurrence** (`app/services/recurrence.last_occurrence()`,
  start + first-occurrence duration) has passed; unbounded/unparseable rules are
  kept. Shared cutoffs live in `app/services/expiry.py` (F22 reuses them).
- **Archiving / GC (F22 + F22.01)** — events are soft-deleted (never hard-deleted)
  by `app/services/archive.archive()`, which stamps `archived_at` +
  `archived_reason` (`"expired"` | `"removed"`). Expired events (past
  `expire_past_days`) archive immediately; removed-at-source events archive only
  after `archive_grace_hours`. Archiving runs automatically at the end of each
  non-dry ingest (`ingest._run()`) and manually via `python -m app.archive`,
  `/debug/archive`, or `POST /api/v1/archive`. The public read path
  (`query_events`/`get_event`) excludes archived rows, as do stats/stale; archived
  events are frozen (F59.01) — they don't un-archive on re-ingest and are ignored
  in the stale count. `stats.stale_events()`
  tags each stale event with `kind` (`"expired"`/`"removed"`). An idempotent
  migration in `init_db()` adds the two columns to existing SQLite DBs. Admin
  visibility/restore (F22.02): `stats.event_dump()` exposes
  `last_seen_at`/`archived_at`/`archived_reason`; `GET /api/v1/archived?limit=`
  lists archived events (most-recent first, capped at `DEFAULT_LIMIT` like
  `/events`) and `POST /api/v1/archived/{id}/restore` un-archives, mirrored by
  `/debug/archived`.
- **Pin / content freeze (F22.03)** — `Event.pinned` freezes an event's content:
  the sieve buckets a pinned existing event as `unchanged` (skips the
  `content_hash` comparison), so source updates are ignored, while
  `last_seen_at` is still stamped and archiving still applies normally
  (pinned events archive when expired/removed). Toggle via
  `POST /api/v1/events/{id}/pin` or `/debug/event/{id}`; `pinned` is exposed in
  `stats.event_dump()` and `list_archived()`. Pin blocks source-driven changes
  only — admin `retag`/`restore`/`unpin` still apply.
- **Event editing (F28)** — full-fidelity edits via
  `POST /api/v1/events/{id}/edit` (or `/debug/event/{id}/edit`): the
  `actions.edit_event()` action coerces the editable fields (title, description,
  location, url, images, start/end, timezone, all_day, rrule, recurrence_id,
  exdates, redirect_to_id, priority, categories) and
  `events.update_event()` applies them, bumps `updated_at`, **recomputes
  `content_hash`**, and pins the event (per-edit `pinned` flag, default true).
  Non-pinned edits are transient — the recomputed hash means the next ingest
  reverts them. `id`/`source_id`/`uid`/derived/operational columns are not
  editable.

## Configuration

Configuration is split into three places: **system** settings (`config.yaml`, the
single source of truth, hand-edited and never written by the program), **auth +
secrets** (`.env` — `admin_username`/`admin_password_hash`/`pepper` + future API
keys; it does **not** override `config.yaml`), and **intake** data (`intake.yaml`,
hand-editable *and* program-editable via `app/intake.py`). All are gitignored with
tracked `*.example` templates.

System fields in `config.yaml`:

- `public_host` / `public_port` — read-only listener (default `0.0.0.0` / `8081`).
- `admin_host` / `admin_port` — debug listener (default `127.0.0.1` / `8082`).
- `data_dir` — SQLite + `last_ingest.json` location (default `data`).
- `database_url` — optional override (defaults to `sqlite:///{data_dir}/ripcale.db`).
- `intake_file` — path to the intake settings file (default `intake.yaml`).
- `expire_past_days` — drop ingested events that fully ended more than N days ago (recurring series only once their last occurrence has passed); `None` disables (default `90`).
- `expire_future_days` — drop ingested events starting more than N days ahead; `None` = no future bound (default).
- `archive_grace_hours` — an event removed at the source is archived only after it has been stale this many hours; `None` disables removed-archiving (default `6`).
- `display_timezone` — IANA zone used to render event times in the admin UI (display-only; storage stays naive-UTC; default `America/New_York`).
- `ingest_interval_minutes` — how often the scheduler runs the full ingest (`None`/`0` disables; default `60`); also the stale-lock timeout.
- `ingest_startup_delay_minutes` — cooldown after admin startup before the scheduler's first ingest (default `3`).
- `debug_now` — fixed naive-UTC ISO timestamp that freezes the backend "now" (debug/time-travel); empty = real clock (F56.01).
- `public_base_url` — base URL used to absolutize local `/images/...` URLs in the ICS feed; empty = ICS falls back to `source_url` (F18).
- `log_file` — rotating log path (relative → `data_dir`; empty → `data/ripcale.log`).
- `log_max_bytes` — rotate once the file reaches this size (default `1000000`).
- `log_backup_count` — rotated backups to keep (default `3`).
- `cors_origins` — CORS origin list (default `*`).
- `debug_allowed_cidrs` — extra IPv4 CIDRs for the admin endpoints (loopback always allowed).
- `debug_token` — optional fixed CSRF token (auto-generated if empty).
- `admin_username` / `admin_password_hash` — bootstrap admin login (argon2id hash; generate with `python -m app.auth hash-password`).
- `pepper` — optional secret keyed (HMAC-SHA256) into every password before hashing (empty = disabled; generate with `python -m app.auth gen-pepper`).

(API tokens are **per-user**, minted in the DB via `python -m app.auth token create <username>` — not an env var.)

Intake fields in `intake.yaml` (`app/intake.py`):

- `gatherers` — per-gatherer defaults, e.g. `{elfsight: {priority: 5}}` (extensible); `rules` apply to every source of that gatherer.
- `rules` — top-level (global) categorization rules, applied to every event from every source.
- `sources` — list of `{name, gatherer, url, is_public, priority, default_categories, default_location, rules}`; an optional source `priority` overrides the gatherer default (fallback 0); optional `default_location` fills missing/blank event locations; `rules` are categorization heuristics (see `docs/CATEGORIZE_CONTRACT.md`).
- `category_symlinks` — `{"class:name": "class:name"}` mapping, resolved at read time by `app/services/categories.resolve_event_categories()` (F26/F51).
- `category_definitions` — class-first `{class: [names, ...]}`; classes are fully dynamic, unlisted names default to `intake`. Names+classes are slugified to `[a-z0-9-]` at the categorize gate (F46/F51).
- `exposed_classes` — list of classes (default `["external"]`) whose categories are the "true", publicly-exposed categories. Every other class is internal-only: kept in the DB but hidden from `/events`, `/feed.ics`, and `/api/v1/events` (F17).

## Maintenance (do this on every change)

- Move the relevant card in `TODO.md` (Backlog → In Progress → Done) as work progresses.
- Add a dated `DEVLOG.md` entry per change (tag AI-authored entries with `[AI]`).
- Update this file whenever architecture, configuration, or invariants change.

The original project vision lives in the repo-root `DEVLOG.md`; the ongoing
development journal is `DEVLOG.md` in this directory.
