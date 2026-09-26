## 2026-09-24 17:00:00 [AI]

F64: recurrence timezone correctness (recurring events no longer drift across DST).

- `app/services/recurrence.py`: new `normalize_rrule()` — normalizes an RRULE's `UNTIL` to compact UTC (`YYYYMMDDTHHMMSSZ`), converting ISO-dashed and local (`TZID`-relative) values to UTC via the event's IANA zone; idempotent. `last_occurrence()` unchanged (still uses `_normalize_until` for dateutil).
- `app/gatherers/ics/gatherer.py`: normalizes `RRULE` at ingest (`normalize_rrule(..., tz=timezone)`); CONTRACT_VERSION → 5.
- `app/services/vtimezone.py` (new): `build(tz_name)` generates an RFC 5545 `VTIMEZONE` (`STANDARD`/`DAYLIGHT` with explicit `DTSTART`/`RDATE` transitions from `dateutil.tz`).
- `app/services/ics.py`: recurring events with a valid `timezone` emit `DTSTART;TZID=<tz>`/`DTEND`/`EXDATE`/`RECURRENCE-ID` in local time; `events_to_ics()` adds a `VTIMEZONE` per recurring zone. One-off/all-day events unchanged (`Z`/`VALUE=DATE`).
- `docs/GATHERER_CONTRACT.md` → v5: UNTIL must be UTC `Z`; recurrence is served as master+rrule (consumers expand); removed the F12 "server-side expansion" block. F12 moved to Deleted.
- Tests: `normalize_rrule` (recurrence), gatherer UNTIL normalization, ICS `TZID`+`VTIMEZONE` (and one-off still `Z`), `vtimezone` builder (DST + no-DST + unknown/UTC). 366 passing.

## 2026-09-24 16:00:00 [AI]

F58.01 follow-up: fail on high/critical by default + scan-error bypass.

- `app/audit.py`: `--fail-severity` now defaults to `high` (was report-only); added `--allow-scan-errors` (downgrades a scanner error to a warning instead of failing, while findings still gate).
- `Dockerfile`: `ARG SCAN_FAIL_ON="high"` and `ARG BUILD_DESPITE_OSV_DOWN=""`; the audit `RUN` conditionally appends `--allow-scan-errors` via `${BUILD_DESPITE_OSV_DOWN:+...}`. Escapes: `SCAN_FAIL_ON=""` (report only) and `BUILD_DESPITE_OSV_DOWN=1` (OSV-outage bypass).
- README/AGENTS updated; 351 tests (added `allow_errors` coverage). Verified `docker compose build` succeeds under the new default gate.

## 2026-09-23 01:00:00 [AI]

F58.01: switch the dependency scanner to osv-scanner + severity-threshold gate.

- Replaced pip-audit with **osv-scanner** (single scanner): it reads `uv.lock` natively and prints a **severity-sorted** table (critical → high → medium → low, with CVSS + fix versions).
- `Dockerfile`: `COPY --from=ghcr.io/google/osv-scanner:latest /usr/local/bin/osv-scanner ...`, `COPY osv-scanner.toml .`, and `RUN python -m app.audit ... --fail-severity "$SCAN_FAIL_ON"` — empty = report only, else fail on an un-acknowledged finding at/above that severity (medium/low/unknown are warnings).
- `app/audit.py` (rewritten): runs osv-scanner, prints its report, parses the `(N Critical, N High, …)` summary line, and applies the severity gate (conservative fail if findings can't be classified).
- `osv-scanner.toml` (new, committed): `[[IgnoredVulns]]` acknowledgement list (id / reason / optional `ignoreUntil`).
- `scripts/audit.sh` (new): local informational docker one-liner.
- Removed the `security`/pip-audit extra from `pyproject.toml` (re-locked `uv.lock`).
- Tests: `tests/test_audit.py` rewritten (summary parsing + severity gate + subprocess wiring; 11 tests).

## 2026-09-23 00:00:00 [AI]

F58: dependency vulnerability scanning (`pip-audit`).

- `pyproject.toml`: new `security` extra (`pip-audit>=2.7.0`) → pinned in `uv.lock` (2.10.1); installed by `--all-extras` locally and in Docker.
- `Dockerfile`: `ARG SCAN_FAIL_ON=""`; after `uv sync`, `pip-audit --skip-editable --format columns || [ -z "$SCAN_FAIL_ON" ]` — always prints the report, fails the build only when `--build-arg SCAN_FAIL_ON=1` is passed. (pip-audit has no severity tiers; it exits 1 on any known vuln.)
- `app/audit.py` (new): `python -m app.audit` thin wrapper (defaults `--skip-editable`, forwards args, propagates exit code).
- Docs: README "Security scanning" section + upgrade workflow; AGENTS.md run-command list + a "Dependency vulnerability scanning (F58)" invariant.
- Tests: `tests/test_audit.py` (wrapper invocation + no-duplicate `--skip-editable`). Verified `python -m app.audit` → "No known vulnerabilities found" (exit 0).
- Also added F60 (SSRF guard), F61 (scrub URLs from errors), F62 (non-root Docker user), F63 (TLS docs) to the backlog + fixed the duplicate `F57.01` → `F57.02`.

## 2026-09-22 23:30:00 [AI]

F18.01 (image GC + re-host on restore), F59 (full event page), F59.01 (archived = frozen).

- **F18.01** — `app/services/images.py`: `referenced_filenames()` (live events only), `prune()` (dry-run default; deletes `data/images/*` files no *live* event references — archived-only images are also removed), `is_local()`, `rehost_missing_images()`. Surfaces: `python -m app.images prune [--commit]`, `POST /api/v1/images/prune`, `/debug/images` (`app/routers/images_admin.py`, registered in `app/admin.py`, linked from `/debug`). `archive.restore()` now re-hosts pruned local images (content-addressed → same bytes land on the same filename) before un-archiving.
- **F59** — `stats.event_dump()` images now carry a `hosted` flag; `/debug/event/{id}` renders **all** fields (uid/description/location/url/timezone/all_day/rrule/recurrence_id/redirect_to_id/priority/content_hash/created/updated/exdates) plus an image gallery with `<img>` previews and a hosted/external badge. `app/routers/images.py` is now also registered on the admin app so previews resolve.
- **F59.01** — `SieveResult` gains `archived_ids` (SIEVE_CONTRACT v4→v5). The sieve buckets an incoming event whose stable id maps to an archived row into `archived_ids` (no `content_hash`, no update); `ingest.process_source` skips `host_images()` for those events; the decisionmaker no longer un-archives on the updated/unchanged paths. Archived events are frozen — they return only via explicit `restore()`.
- Tests: +11 (338 passing) — sieve frozen, prune dry-run/commit/archived-only, re-host present/missing/external, restore re-host, `/api/v1/images/prune`, `/debug/images`, full event page.

## 2026-09-22 22:30:00 [AI]

B01: SQLModel timezone bug (Docker login/ingest broken) + `uv` lockfile.

- Root cause: the latest SQLModel (0.0.43+) enforces **timezone-aware** datetimes by default ("Datetime values must have timezone information"), but ripcale stores **naive UTC** everywhere. The local venv was pinned to the older 0.0.42 (no enforcement), while a fresh Docker `pip install ".[dev]"` resolved the loose `sqlmodel>=0.0.21` to 0.0.46 — so `init_db()`/`ensure_admin_user()` (naive `User.created_at`), login (naive `LoginSession.expires_at`), and ingest (naive `Event.start_at` etc.) all failed in Docker.
- Fix: every naive datetime field in `app/models.py` now declares an explicit `sa_column=Column(DateTime(timezone=False))` (via a shared `_dt()` helper; `index=True` kept on `Event.start_at`/`Event.archived_at`). This is version-agnostic — it works under both 0.0.42 and 0.0.46.
- `pyproject.toml` dependency pinning is now locked with **uv**: added `uv.lock` (sqlmodel pinned to 0.0.46; 46 packages). The `Dockerfile` now copies `uv.lock` and installs via `uv sync --frozen --all-extras` (venv at `/app/.venv`, added to `PATH`). Local dev: `uv sync --all-extras` instead of `pip install -e`.
- Verified: 327 tests pass under 0.0.46; `docker compose build` + `up` boots clean (User row created with naive `created_at`), `healthz` OK, login returns clean 401, and a full ingest stored 524 events with naive `start_at`.

## 2026-09-08 06:40:00 [AI]

F18: local image hosting (pre-sieve).

- `app/config.py`: `public_base_url: str = ""` (absolutize local image URLs in ICS).
- `app/services/images.py` (new): `store()` (content-addressed `{data_dir}/images/<sha256>.<ext>`, atomic write), `resolve()` (traversal guard), `host_images()` (rewrite `url`→local, `source_url`→origin; graceful on failure).
- `app/ingest.py`: `host_images()` runs after `gather`, before `categorize`/`sieve`.
- `app/identity.py`: `content_hash` now hashes images by **`img.url` only** (not `alt`/`source_url`) — the stable local URL is the identity. One-time "updated" churn documented.
- `app/routers/images.py` (new) + `app/public.py`: `GET /images/{filename}` via `robyn.serve_file`.
- `app/services/ics.py`: `ATTACH`/`X-RIPCALE-IMAGE` use `public_base_url`-absolutized local URLs, else fall back to `source_url`.
- Tests: `test_images.py` (store/dedup/ext/guard/endpoint), `test_identity.py` (url-only image hash), `test_ics.py` (absolute/fallback); conftest stubs `httpx.get` so tests never hit the network (327 passing).

## 2026-09-08 06:20:00 [AI]

Generic ICS tags (drop instance name "rva.rip" from the calendar output).

- `app/services/ics.py`: `X-RVA-SOURCE`/`X-RVA-TIMEZONE`/`X-RVA-IMAGE` → `X-RIPCALE-SOURCE`/`X-RIPCALE-TIMEZONE`/`X-RIPCALE-IMAGE`; `PRODID` → `-//ripcale//ripcale//EN`; default `X-WR-CALNAME` title → `"ripcale"`.
- `docs/GATHERER_CONTRACT.md` + `tests/test_ics.py` updated to the new tags (317 passing).

## 2026-09-08 06:00:00 [AI]

F21.03: Instagram image-reading pipeline (design map — read each image once per update).

- OCR runs **post-sieve** (not in the gatherer). The sieve already yields `new`/`updated` vs `unchanged`, and `content_hash` includes `images`, so OCR only fires when an event is new or its content (incl. images) changed.
- **Per-image cache** keyed by image URL (or a hash of the bytes) → extracted text. On re-ingest, only *new* image URLs are OCR'd; unchanged images reuse the cached text. This is the "read once per update" guarantee, naturally.
- Output must be persisted so downstream stages (categorize / decisionmaker / F14) can use it to pull title/date/time/location out of flyers.
- Open forks for the implementation ticket (F40): where OCR results live (Event column vs a separate `ocr` table), whether OCR runs synchronously in the pipeline or async/queued, and retry policy on failed OCR.

## 2026-09-08 05:50:00 [AI]

F21.02: OCR for artistic flyer text (Chinese tech + stable interface + affordable).

- Requirement (updated): handle artistic/stylized text, prefer an **extremely stable interface**, and prefer **Chinese technology** ("like DeepSeek").
- Correction: **DeepSeek's public API is text-only** (V3/R1; no strong public vision/OCR endpoint — its VL variants are open-weights, not the maintained product line). So it points at the right *category* but isn't the vendor for images.
- Recommendation: **Alibaba Qwen2.5-VL** as primary — best-in-class OCR/document understanding + key-information extraction (ideal for flyers), open-weights (3B/7B/72B), stable interface both on the managed **DashScope** API and self-hosted (ollama/vLLM), and affordable (cheap per-token; the 3B/7B self-host is ~zero marginal cost on a single GPU).
- Alternatives: Baidu PaddleOCR/PP-ChatOCR (self-host, stable Python lib; classic PaddleOCR weaker on stylized text), Baidu ERNIE-VL/Qianfan, Tencent Hunyuan, Zhipu GLM-4V.

## 2026-09-08 05:40:00 [AI]

F21.01: Instagram source research — HikerAPI confirmed.

- HikerAPI is a third-party Instagram data API: public profiles, **posts/reels**, stories, hashtags, locations — **no OAuth, no Instagram account**, pay-per-request, 100 free requests. Matches "watch specific public event pages" exactly.
- Alternatives weighed: Instagram **Graph API** (official — only for accounts you own/manage, so unsuitable), **Instaloader** (free but needs your own login + rate-limit/ban risk + fragile vs Meta changes), **Apify** Instagram scrapers (works but general-purpose/pricier for this narrow use).
- Decision: use HikerAPI; keep the gatherer swappable behind the standard `run(source)` interface (URL = API/account config) so no HikerAPI-specific logic leaks elsewhere.

## 2026-09-08 05:20:00 [AI]

F56.03: single source of truth for config (config.yaml authoritative; `.env` = auth/secrets only).

- `app/config.py`: reordered `settings_customise_sources` to `init > config.yaml > env > dotenv > defaults`, so `config.yaml` wins and env/`.env` only fill gaps (secrets not defined there).
- `config.example.yaml`: removed the `admin_username`/`admin_password_hash`/`pepper` block (auth lives in `.env`); clarified the header.
- `.env.example`: dropped the system "Overrides" block; now documents only `RIPCALE_ADMIN_USERNAME`/`RIPCALE_ADMIN_PASSWORD_HASH`/`RIPCALE_PEPPER` + future keys.
- Docs: AGENTS.md + README.md configuration sections updated (authoritative config.yaml; `.env` = auth/secrets, no override).
- Tests: precedence test (yaml beats .env; auth from .env) (317 passing).

## 2026-09-08 05:00:00 [AI]

F56.01: central clock + debug time-travel.

- `app/config.py`: `debug_now: str | None` — a fixed naive-UTC ISO instant that freezes the backend "now".
- `app/services/clock.py` (new): `now()` (frozen instant when set, else `utcnow()`) + `debug_active()`; re-parses only when the config value changes.
- Threaded `clock.now()` into domain logic: `decisionmaker.apply` (`run_ts`), `sieve.classify` default `now`, `archive` default `now`, `stats._now()` (upcoming/past/stale). Auth session expiry + `created_at`/`updated_at` stay on the real clock.
- Served to the frontend via an `X-Server-Time` header on `/events` + `/events/{id}` (`app/routers/events.py::_json`); `app/public.py` adds `Access-Control-Expose-Headers: X-Server-Time` (Robyn's `ALLOW_CORS` doesn't set expose-headers).
- `/debug` shows a "debug clock (frozen)" banner when active.
- Tests: `test_clock.py` (real/frozen/aware-normalized/invalid), `test_events.py` (header + CORS expose), `test_archive.py` (archive respects the debug clock) (316 passing).

## 2026-09-08 04:30:00 [AI]

F25: generic `ics` gatherer (Google Calendar + any RFC 5545 feed).

- `app/gatherers/base.py`: added `fetch_text(url)` (next to `fetch_json`).
- `app/gatherers/ics/{__init__,__main__,gatherer}.py` (new, `CONTRACT_VERSION = 4`): fetches an `.ics` feed and maps every `VEVENT` → `ScrapedEvent`.
  - Handles `DTSTART`/`DTEND` as `…Z` (UTC), `;TZID=…` (aware, via VTIMEZONE/ZoneInfo), and `VALUE=DATE` (all-day).
  - Maps `UID`/`SUMMARY`/`DESCRIPTION`/`LOCATION`/`URL`/`CATEGORIES`/`RRULE`/`RECURRENCE-ID`/`EXDATE`/image `ATTACH`.
  - **STATUS** is lowercased into a category (`confirmed`/`tentative`/`cancelled`/…), generic over any value.
  - `raw` keeps unmodeled metadata (sequence/dtstamp/created/last-modified/transp) for debugging.
- `intake.example.yaml`: Gold Lion + Coalition Theater `ics` source examples.
- Tests: `tests/test_gatherer_ics.py` (UTC/TZID/all-day/recurrence+EXDATE/status tags/override); contract test auto-discovers the new gatherer (310 passing).

## 2026-09-08 04:00:00 [AI]

F11: automatic ingest scheduler + ingest lock.

- `app/config.py`: `ingest_interval_minutes: int | None = 60` (scheduler cadence + stale-lock timeout) and `ingest_startup_delay_minutes: int = 3`.
- `app/services/scheduler.py` (new): daemon thread — waits the startup cooldown, then runs `run_report(dry_run=False)` every interval; `status()` exposes `enabled`/`interval_minutes`/`last_run_at`/`next_run_at`/`running`.
- `app/services/lock.py` (new): cross-process `{data_dir}/ingest.lock` (atomic `O_CREAT|O_EXCL`, stale after one interval) guarding `ingest._run()`.
- `app/ingest.py`: `_run()` now wraps the pipeline body in the lock; on contention returns a `skipped` summary.
- `app/admin.py`: `start_scheduler()` on boot.
- Expose: `actions.scheduler()`, `GET /api/v1/scheduler`, and a `/debug` "ingest scheduler" line (local+UTC via `display_time`).
- Tests: `test_scheduler.py`, `test_lock.py`, config defaults, API + debug (306 passing).

## 2026-09-08 03:40:00 [AI]

F44: poll-based auto-deploy guide + files.

- `deploy/deploy.sh`: `git pull --ff-only` and `docker compose up -d --build` only when HEAD moved.
- `deploy/ripcale-deploy.service` + `deploy/ripcale-deploy.timer`: systemd oneshot + 5-minute timer (reference units).
- `docs/DEPLOYMENT.md`: full guide (server setup, gitignored config, public/private git auth, timer install, manual deploy, branch switching, troubleshooting).
- README links the deployment doc; AGENTS notes the deploy script + timer. No CI/SSH into the server — the server pulls outbound.

## 2026-09-08 03:10:00 [AI]

F28.02: display timezone (admin UI shows local + UTC).

- `app/config.py`: `display_timezone: str = "America/New_York"` (display-only; storage stays naive-UTC).
- `app/timeutil.py`: `display_time(dt)` — formats a naive-UTC time as `local TZ · … UTC` via `ZoneInfo` (DST-correct; falls back to UTC on empty/invalid zone; collapses to a single `… UTC` when the zone is UTC).
- `app/services/stats.py`: `event_dump()` gains `start_at_display`/`end_at_display`; `app/services/actions.py`: `event_list()` gains the same.
- `app/routers/debug.py` (`/debug/events`) + `app/routers/event.py` (`/debug/event/{id}`) show the localized times.
- Tests: `tests/test_timeutil.py` (EDT/EST/rollover/None/invalid-zone/UTC) + display fields in `event_list`/`event_dump`/debug render (294 passing).

## 2026-09-08 02:50:00 [AI]

F28.01: admin events list page.

- `app/services/actions.py`: `event_list(limit, category)` — admin listing of live events (raw stored categories + `pinned`; no symlink/exposure resolution), via `query_events` + `source_names`.
- `app/routers/debug.py`: `GET /debug/events` (HTML table, title → `/debug/event/{id}`), `?limit=`/`?category=` filters, linked from the dashboard.
- Tests: `event_list` shape/order/limit/category + `/debug/events` render (288 passing).

## 2026-09-08 02:30:00 [AI]

F28: full-fidelity event editor (API-first + no-JS HTML).

- `app/services/events.py`: `update_event(session, id, fields, *, pinned)` — applies an editable-field whitelist, bumps `updated_at`, pins, and recomputes `content_hash` via `_recompute_hash()` (rebuilds a `ScrapedEvent` from the row).
- `app/services/actions.py`: `edit_event()` — coerces input (ISO datetimes, categories, images/exdates JSON, all_day/pinned/priority) with `ActionError` on bad input / 404 on missing; commits + returns the updated dump.
- `app/services/stats.py`: `event_dump()` now includes `priority`.
- `app/routers/api.py`: `POST /api/v1/events/{id}/edit` (partial update).
- `app/routers/event.py`: `GET/POST /debug/event/{id}/edit` (no-JS form, `images`/`exdates` as JSON textareas, per-edit `pin` checkbox default checked) + an "edit" link on the event page.
- Non-pinned edits are transient by design (recomputed hash → next ingest reverts).
- Tests: service (apply/pin/rehash/missing), action (parsing + 404 + bad date/JSON), API edit, debug edit form, `event_dump` priority (285 passing).

## 2026-09-08 02:00:00 [AI]

F22.04–F22.09: archive/expiry/pin integration-test hardening.

- `tests/test_ingest.py`: end-to-end archive lifecycle (expired → `ingest.run()` archives → `query_events` excludes → `archive.restore` brings it back); pin end-to-end (`process_source` with a changed source leaves a pinned row's content + hash unchanged while `last_seen_at` stamps).
- `tests/test_decisionmaker.py`: restore-on-reseen via the `updated` path (archived + changed content → un-archived + updated).
- `tests/test_debug.py`: `overview()["archived"]` count + `sources()` excludes archived.
- `tests/test_recurrence.py`: `is_expired` "last occurrence + duration" boundary (duration tips the verdict).
- `tests/test_archive.py`: `archive()` idempotency (second run archives nothing).
- 279 passing.

## 2026-09-08 01:40:00 [AI]

F22.03: pin events (content freeze, archive unaffected).

- `app/models.py`: `Event.pinned: bool = False`; `app/db.py` migration adds the `pinned` column.
- `app/sieve/sieve.py`: a pinned existing event is bucketed `unchanged` (content_hash comparison skipped), so source updates are ignored while `last_seen_at` still stamps.
- `app/services/events.py`: `set_pinned()`; `app/services/actions.py`: `pin(event_id, pinned)` (returns the new state).
- `app/routers/api.py`: `POST /api/v1/events/{id}/pin`; `stats.event_dump()` + `list_archived()` expose `pinned`.
- `app/routers/event.py` (new): `/debug/event/{id}` (view + pin/unpin + restore), registered in `app/admin.py`; `/debug/archived` + `/debug/stale` rows link to it.
- Tests: sieve pinned-unchanged, archive still archives pinned-expired, set_pinned, API pin, migration, event page + pin (273 passing).

## 2026-09-08 01:20:00 [AI]

F22.02: admin archive management + capped listings.

- `app/services/stats.py`: `event_dump()` now exposes `last_seen_at` / `archived_at` / `archived_reason`.
- `app/services/archive.py`: `DEFAULT_ARCHIVE_LIMIT = DEFAULT_LIMIT` (500); `list_archived()` (desc by `archived_at`, capped); `restore()` (un-archive); `archive()` preview capped + ordered by reference time desc.
- `app/services/actions.py`: `archived(limit)` + `restore(event_id)`.
- `app/routers/api.py`: `GET /api/v1/archived?limit=` + `POST /api/v1/archived/{id}/restore`.
- `app/routers/archive.py`: `/debug/archived` (list + per-row restore) + `POST /debug/archived/{id}/restore`; dashboard link added.
- Tests: archive listing/restore, event_dump fields, API list+restore, default-limit parity (267 passing).

## 2026-09-08 01:00:00 [AI]

F22 + F22.01: archive (soft-delete) + expired/removed distinction.

- `app/models.py`: `Event.archived_at` (indexed) + `Event.archived_reason` (`"expired"` | `"removed"`).
- `app/db.py`: idempotent migration (`PRAGMA table_info` → `ALTER TABLE ADD COLUMN` + index) in `init_db()` so existing SQLite DBs gain the columns.
- `app/services/expiry.py`: extracted shared `is_expired()` (rrule-aware) used by both F13 `is_relevant()` and F22.
- `app/services/archive.py` (new): `archive()` — expired (past `expire_past_days`) immediately; removed-at-source only after `archive_grace_hours` (default 6h). Soft-deletes via `archived_at`/`archived_reason`.
- `app/config.py`: `archive_grace_hours: int | None = 6`.
- Read path excludes archived: `query_events()`/`get_event()` filter `archived_at IS NULL`; `stats.overview()`/`sources()` exclude archived (overview gains `archived` count); `stats.stale_events()` excludes archived and tags each stale event with `kind`.
- `app/decisionmaker.py`: re-seen events un-archive (updated + unchanged paths); stale query ignores archived rows.
- `app/ingest.py`: auto-runs archiving at the end of non-dry ingests; report includes `archived`.
- Surface: `actions.archive()`, `POST /api/v1/archive`, `/debug/archive` page, `python -m app.archive` CLI; `/debug/stale` shows `kind`.
- Tests: `test_archive.py`, stale `kind`, archived-exclusion (events/get), restore-on-reseen, migration, config, ingest auto-run, API archive (260 passing).

## 2026-09-08 00:30:00 [AI]

F13.01 + F13.02: expiry-filter fixes.

- `app/config.py`: `expire_past_days: int | None = 90` (was non-nullable `int`, so the documented "set null to disable" would raise at startup).
- `app/services/recurrence.py`: `last_occurrence()` now normalizes RFC 5545 `UNTIL` (`…Z` suffix stripped, ISO-dashed dates collapsed) and explicitly returns `None` for unbounded rules (no `COUNT`/`UNTIL`) — previously an unbounded rule leaked dateutil's `9999` sentinel instead of `None`.
- Tests: `tests/test_config.py` + `tests/test_recurrence.py` (243 passing).

## 2026-09-08 00:15:00 [AI]

F13: relevance/expiry filter in the sieve.

- `app/config.py`: `expire_past_days: int = 90` + `expire_future_days: int | None = None` (relevance window).
- `app/services/expiry.py` (new): shared `past_cutoff`/`future_cutoff` + `is_relevant(...)` (F22 GC reuses the cutoffs).
- `app/services/recurrence.py` (new): `last_occurrence(rrule, start_at)` — the final instance of a bounded RRULE (None = unbounded/unparseable); F12 expansion will build here.
- `app/sieve/sieve.py`: `_relevance(events, now)` filters via `expiry`; `classify(..., now=None)` injectable; `SieveResult.dropped` counts filtered events. Recurring series expire only when last occurrence (start + first-occurrence duration) is past the window.
- `app/schema.py`: `SieveResult.dropped`; `SIEVE_CONTRACT.md` v4 (+ `CONTRACT_VERSION = 4`); `ingest.py` summary surfaces `dropped`.
- `pyproject.toml`: `python-dateutil` declared directly.
- Tests: relevance cases (past/future drop, unbounded-rrule kept, bounded-rrule expired/recent, null dates, disabled pass-through); sieve + contract tests updated (233 passing).

## 2026-09-07 23:45:00 [AI]

F29: category & symlink mapping on /debug (collapsed) + `/api/v1/categories`.

- `app/services/categories.py`: `is_exposed()` promoted to public (used by the mapping view + `expose()`).
- `app/services/actions.py`: `category_mapping()` returns `{definitions, symlinks, exposed_classes, categories}` where `categories` is the DB count breakdown enriched with `class` + `exposed` (fail-safe intake load). Dropped the now-unused `symlinks()`.
- `app/routers/debug.py`: the categories table gains `class`/`exposed` columns, plus a collapsed `<details>` "category mapping (config)" section (exposed classes, definitions, symlinks).
- `app/routers/api.py`: `GET /api/v1/categories` → `category_mapping()`.
- Tests: `test_actions.py` + `test_api.py` + `test_categories.py` coverage (226 passing).

## 2026-09-07 23:30:00 [AI]

F17: true-category exposure (class-gated public categories).

- `app/intake.py`: `IntakeSettings.exposed_classes: list[str]` (default `["external"]`) — the classes whose categories are the public "true" categories.
- `app/services/categories.py`: `exposed_classes()` (memoized frozenset), `expose()` (drop non-exposed categories), and `resolve_event_categories()` now resolves symlinks **then** filters to exposed classes. The low-level `resolve_categories()` stays unfiltered.
- Public read path (`/events`, `/events/{id}`, `/feed.ics`, `/api/v1/events`) now exposes only "true" categories; internal `intake:*` categories stay in the DB but are hidden. Admin raw views (`/debug`, `/debug/stats`, `/debug/events/:id`) unchanged.
- `app/services/coherence.py`: warnings when an `exposed_classes` entry isn't defined in `category_definitions`, and when a symlink target resolves to a non-exposed class.
- Tests: exposure filtering (categories/events/ics/intake/coherence); 223 passing.

## 2026-09-07 23:00:00 [AI]

F48.05 + F48.06: DB-backed credentials + per-user API tokens (unified auth).

- `app/models.py`: `LoginSession` (token, user_id FK, expires_at) + `ApiToken` (sha256 token_hash, user_id FK, label, created_at).
- `app/services/auth.py`: sessions moved to DB (`create_session(user_id)`/`validate_session`→user_id/`destroy_session`); per-user tokens (`create_api_token` stores the hash + returns the raw once, `validate_api_token`, `revoke_api_token`, `list_api_tokens`).
- `app/security.py`: `authenticated_user(request)` (session cookie **or** bearer → user_id); `session_guard`/`api_guard` unified to it. Removed `verify_api_token` and the shared `api_token`.
- Removed `api_token` from `config.py`, `admin.py`, `coherence.py`, `config.example.yaml`, `.env.example`, `conftest.py`.
- `app/db.py`: `wipe_db()` now also deletes `LoginSession` + `ApiToken`.
- `app/auth.py` CLI: `token create/list/revoke` (subparser-based); user commands `init_db()` first.
- Tests: `test_auth.py` (sessions, tokens, hashed-storage, expiry), `test_api.py` (per-user bearer + session-cookie auth), `test_coherence.py` (api_token cases removed); `session_headers` fixture mints a session in a temp engine (213 passing).

## 2026-09-07 22:10:00 [AI]

Command reference + auth CLI fix.

- `README.md`: added a "Command reference" section (grouped code blocks) covering every entrypoint — servers, ingest, `app.debug`, `app.auth`, dev/Docker.
- `app/auth.py`: user-management subcommands now call `setup_logging()` + `init_db()` first, so `add-user`/`change-password`/`remove-user`/`list-users` work on a fresh install (previously failed on a missing `user` table).

## 2026-09-07 22:00:00 [AI]

F48.04 + F48.01: multi-user management + account lockout.

- `app/services/auth.py`: `create_user`/`change_password`/`remove_user`/`list_users`; account lockout (`LOCKOUT_THRESHOLD`/`LOCKOUT_DURATION`, `_lockouts`/`_failures`) — `login()` returns 423 "account locked" before checking the password, keeps the 429 rate limiter.
- `app/auth.py` CLI: `add-user`, `change-password`, `remove-user`, `list-users`.
- Tests: `tests/test_auth.py` (user CRUD, rate-limit isolated from lockout, lock + expiry) — 212 passing.

## 2026-09-07 21:30:00 [AI]

F48.07: argon2 hardening.

- `app/config.py`: `pepper: str = ""` (optional; empty = disabled); `config.example.yaml` note.
- `app/services/auth.py`: pinned `ARGON2_TIME_COST`/`MEMORY_COST`/`PARALLELISM` passed to `PasswordHasher`; `_apply_pepper()` (HMAC-SHA256, no-op when empty) used by `hash_password`/`verify_password`; `needs_rehash()`; `login()` transparently re-hashes stale-parameter hashes.
- `app/auth.py`: `gen-pepper` command (prints a 256-bit pepper).
- Tests: `tests/test_auth.py` (pepper keys password, needs_rehash, login rehash) — 207 passing.

## 2026-09-07 21:00:00 [AI]

F48: authentication groundwork (admin-side only).

- `pyproject.toml`: added `argon2-cffi`.
- `app/models.py`: `User` table (`username` unique, `password_hash` argon2id).
- `app/config.py`: `admin_username` / `admin_password_hash` (bootstrap); `config.example.yaml` note.
- `app/services/auth.py` (new): argon2id `hash_password`/`verify_password`, in-memory opaque sessions (`create/validate/destroy`, 24h TTL), `login()` (timing-safe dummy verify + generic "invalid credentials" + rate limit 429 after 5/5min), `ensure_admin_user()`.
- `app/security.py`: `json_body()`, `cookie_value()`, `session_guard()` (IP + session cookie).
- `app/routers/auth.py` (new): `POST /api/v1/auth/login|logout` + `/debug/login` (HTML form), `HttpOnly`+`SameSite=Strict` cookies.
- `app/admin.py`: registers auth router + bootstrap admin creation + warnings; `/debug` dashboard now `session_guard`-gated (redirect to `/debug/login`).
- `app/auth.py`: `python -m app.auth hash-password` CLI.
- `app/routers/api.py`: `_json_body` moved to `security.json_body` (deduped).
- Tests: `tests/test_auth.py` (12 tests — hash/verify, login success/wrong/unknown/rate-limit, session validate/expiry/destroy, bootstrap idempotence, routes) + `session_headers` fixture in conftest; dashboard tests now authenticate (204 passing).
- Follow-ups filed: F48.01 (lockout), F48.02 (WebAuthn), F48.03 (OIDC), F48.04 (multi-user CLI), F48.05 (DB sessions), F48.06 (unify session+bearer).

## 2026-09-07 20:20:00 [AI]

F53: HTML debug pages become thin clients of shared actions.

- `app/services/actions.py` (new): request-agnostic read/write/pipeline operations (`overview`, `sources`, `events`, `event`, `stale`, `coherence`, `logs`, `status`, `symlinks`, `ingest`, `retag`, `wipe_begin/confirm`, `tests_list/run`, `gather/sieve/decide/categorize`) + `ActionError` + shared `resolve_source_spec`/`parse_rules`.
- `app/routers/api.py` → thin `{ok,data|error}` envelope over the actions (added `/api/v1/status`).
- HTML routers (`debug`, `retag`, `wipe`, `ingest`, `tests`, `pipeline`) now call the same actions; wipe unified to challenge-response (arm/sentence removed).
- Tests: `tests/test_actions.py` (new) + updated router tests to monkeypatch `actions.engine`; `test_wipe.py` rewritten for challenge-response (192 passing).

## 2026-09-07 20:00:00 [AI]

F54: JSON admin API hardening.

- `app/routers/api.py`: robust `_json_body()` (`request.json()` then `request.body` fallback); a `_route` decorator wrapping every handler with `api_guard` + `try/except → {ok:false, error}` (no raw 500 HTML); `dry_run` echoed on `ingest`; challenge-response wipe (`POST /api/v1/wipe/begin` → token, `POST /api/v1/wipe/confirm` with the token → wipe, 60s TTL); `GET /api/v1/events` enumeration (reuses `query_events`/`to_fullcalendar`).
- Tests: `tests/test_api.py` (10 tests — wipe challenge flow, events enumeration, ingest dry_run echo, error envelope) — 186 passing.

## 2026-09-07 19:45:00 [AI]

Missing-api_token signal.

- `app/admin.py`: log a warning at startup when `api_token` is unset (`/api/v1/* is disabled`).
- `app/services/coherence.py`: `_check_config()` reports a warning issue when `api_token` is empty (surfaces on `/debug`).
- Tests: `conftest.py` sets a placeholder `api_token` so valid-config checks stay clean; `tests/test_coherence.py` gains missing/configured cases (185 passing).

## 2026-09-07 19:30:00 [AI]

F52: JSON admin API (`/api/v1/*`).

- `app/config.py`: `api_token: str = ""` (empty = API disabled); `config.example.yaml` note.
- `app/security.py`: `verify_api_token()` (constant-time `secrets.compare_digest` on `Authorization: Bearer`) + `api_guard()` (IP allowlist → 404, unconfigured → 503, bad token → 401).
- `app/routers/api.py` (new, registered in admin): versioned `{ok, data|error}` JSON surface — GET `stats`/`sources`/`events/:id`/`stale`/`coherence`/`logs`/`tests`, POST `ingest`/`retag`/`wipe`/`tests`/`pipeline/gather|sieve|decide|categorize` — all thin wrappers over services (dry-run default true).
- Convention recorded in AGENTS.md: "Admin/debug interactivity is API-first"; added F53 (migrate existing HTML pages to the API).
- Tests: `tests/test_api.py` (9 tests — auth 401/503, envelope, retag dry-run vs commit, wipe confirm, ingest empty, pipeline gather) — 183 passing.

## 2026-09-07 19:00:00 [AI]

F47: mass retag (rename/remove a category across the whole DB).

- `app/services/retag.py` (new): `_replace_token()` (exact `class:name` token replace/remove) + `retag(session, from_cat, to_cat=None) -> (changed, preview)`. Categories-only edit — content_hash/updated_at untouched.
- `app/routers/retag.py` (new, registered in admin): `/debug/retag` with a `from`/`to` form, dry-run checkbox (default), preview + commit; IP+CSRF gated. Linked from `/debug`.
- Tests: `tests/test_retag.py` (7 tests: token replace, rename/remove, no partial match, dry-run vs commit, CSRF) — 174 passing.

## 2026-09-07 18:40:00 [AI]

F50.05: categorize playground (`/debug/pipeline/categorize`).

- `app/categorize/categorize.py`: extracted `resolve_rules(source)` (public) + `apply(source, events, rules=None)` (explicit-rule override); `CONTRACT_VERSION` 4→5. `app/categorize/__init__.py` re-exports `resolve_rules`.
- `app/ingest.py`: `process_source(..., rules=None)` threads the override to `categorize()`.
- `docs/CATEGORIZE_CONTRACT.md` v5 (signature + `resolve_rules` + rules override).
- `app/routers/pipeline.py`: new categorize stage — single custom rule (mode/fields/regex/categories), "include configured rules" + "dry-run" checkboxes; dry-run shows `[title, categories]`, commit runs `process_source(rules=...)` (one-off, ephemeral). Linked from `/debug/pipeline`.
- Tests: `test_categorize.py` (resolve_rules + rules override), `test_pipeline_playground.py` (dry-run vs commit) — 167 passing.

## 2026-09-07 18:25:00 [AI]

F50.04: single implementation, locked by guard tests.

- The category-assignment engine is already single (`app/categorize/categorize.py` — `apply()` resolves all scopes into one flat list, `_apply_rule()` is the only interpreter of `CategoryRule`, `default_categories` is sugar for an `assign` rule).
- Added two guard tests to `tests/test_categorize.py`: `default_categories` == explicit `assign` rule, and the same rule across global/gatherer/source scopes yields identical output (164 passing).

## 2026-09-07 18:20:00 [AI]

F50.03: closed as already-satisfied.

- The `assign` mode was implemented during F50's `default_categories` unification (`CategoryRule.mode: "regex" | "assign"`, handled by `_apply_rule`, documented in `docs/CATEGORIZE_CONTRACT.md`, validated by coherence, shown in `intake.example.yaml`). No separate work needed; marked Done.

## 2026-09-07 18:10:00 [AI]

F50.02: global-scope categorization rules.

- `app/intake.py`: `IntakeSettings.rules: list[CategoryRule]` (top-level, applies to all events).
- `app/categorize/categorize.py`: `_global_rules()` + `apply()` order is now `global → gatherer → default_categories → source`; `CONTRACT_VERSION` 3→4.
- `docs/CATEGORIZE_CONTRACT.md` v4; `app/services/coherence.py` validates global rules.
- `intake.example.yaml`: commented global `rules:` example.
- Tests: `test_categorize.py` (global apply + combine), `test_intake.py` (rules default/round-trip), `test_coherence.py` (global invalid regex) — 162 passing.

## 2026-09-07 17:50:00 [AI]

F51: `class:name` category identity + slug normalization.

- `app/services/categories.py`: `slugify()` (`[a-z0-9-]`, spaces→dashes, collapse+trim), `qualify(name) -> class:name`, dynamic classes (removed `INTAKE`/`EXTERNAL`; only `DEFAULT_CLASS = "intake"`), `resolve_categories`/`resolve_event_categories` are now symlink-only (`class:name` in → `class:name` out).
- `app/categorize/categorize.py`: after rules, slugifies + qualifies every name to `class:name` before the sieve; `CONTRACT_VERSION` 2→3.
- `docs/CATEGORIZE_CONTRACT.md` v3 (identity + slug normalization section).
- `app/services/coherence.py`: dropped "unknown class" warning (classes dynamic); added non-slug class warning; slug-aware multi-class check.
- Config: `intake.example.yaml` symlinks rewritten as `"intake:visual-arts": "external:art"`.
- Tests: `test_categories.py` rewritten for class:name/slug semantics; `test_categorize.py`, `test_coherence.py`, `test_pipeline.py` updated (159 passing).
- Migration: wipe + re-ingest (categories changed from names to `class:name`; `content_hash` changed).

## 2026-09-07 17:30:00 [AI]

F50.01: gatherer-scope categorization rules.

- `app/schema.py`: `GathererConfig.rules: list[CategoryRule]`.
- `app/categorize/categorize.py`: `_gatherer_rules()` + `apply()` now resolves rules in order `gatherer → default_categories → source`; `CONTRACT_VERSION` 1→2.
- `docs/CATEGORIZE_CONTRACT.md` v2 (gatherer rules in semantics); `docs/GATHERER_CONTRACT.md` v4 (GathererConfig `rules`); `elfsight` re-stamped v4.
- `app/services/coherence.py`: `_check_rules` now also validates gatherer-level rules.
- Tests: `test_categorize.py` (gatherer/combined/unrelated-scope), `test_contract_gatherer.py` (GathererConfig fields), `test_coherence.py` (gatherer invalid regex) — 157 passing.

## 2026-09-07 17:10:00 [AI]

F50: categorization rule engine (new `categorize` stage).

- `app/schema.py`: `CategoryRule` (`mode` regex/assign, `fields`, `regex`, `categories`) + `SourceConfig.rules`.
- `app/categorize/categorize.py` (new, `CONTRACT_VERSION = 1`): `apply(source, events)` — implicit `assign` from `default_categories` + explicit `rules`, matched against `TEXT_FIELDS` (uid/title/description/location/url), categories sorted+deduped, applied before hashing.
- `app/ingest.py`: `process_source` now runs `categorize` between gather and sieve.
- `app/sieve/sieve.py`: dropped `_merge_default_categories` (moved to categorize), `CONTRACT_VERSION` 2→3; `docs/SIEVE_CONTRACT.md` v3.
- `docs/CATEGORIZE_CONTRACT.md` (new, v1); `docs/GATHERER_CONTRACT.md` v3 (SourceConfig gains `rules`); `elfsight` gatherer re-stamped v3.
- `app/services/coherence.py`: validates rules (missing/invalid regex, unknown field).
- Tests: `tests/test_categorize.py` (behavior + before-hash re-classification), `tests/test_contract_categorize.py`, coherence rule checks (153 passing); `test_sieve`/`test_pipeline` updated for the new stage.

## 2026-09-07 16:50:00 [AI]

F26: category symlinks (read-time, external-only).

- `app/services/categories.py`: `resolve_categories()` + `resolve_event_categories()` (map via `category_symlinks`, pass through unmapped, dedupe + sort).
- Wired into `app/serializers.py` (extendedProps.categories), `app/services/events.py` (`?category=` filter), `app/services/ics.py` (CATEGORIES).
- `app/routers/debug.py`: "categories" table gains a forward "symlink" column (`→ external`); the `load_intake()` call is wrapped so a broken intake.yaml can't break `/debug`.
- Tests: `tests/test_categories.py` (139 passing) — resolver + serializer/filter/ICS/debug integration.

## 2026-09-07 16:35:00 [AI]

F49: config/intake coherence checks.

- `app/services/coherence.py` (new): `check()` returns issues `{severity, scope, message}` — intake structure (YAML/shape validation), semantic (gatherer existence, category multi-class/unknown-class/self-symlink), config sanity (`data_dir` writable). Every check is defensive; `check()` never raises.
- `app/routers/debug.py`: a fail-safe "coherence" section at the top of `/debug` (🟢 all good / 🔴🟡 list); the `coherence_check()` call is wrapped so a broken check can never lock out the dashboard.
- Tests: `tests/test_coherence.py` (130 passing) — structural + semantic + route rendering.

## 2026-09-07 16:10:00 [AI]

F46: category classes (intake vs external).

- `app/intake.py`: `IntakeSettings.category_definitions` — class-first `{class: [category, ...]}`.
- `app/services/categories.py` (new): `INTAKE`/`EXTERNAL`/`DEFAULT_CLASS` + `category_class(name)` (scans class lists; unlisted → `intake`).
- `intake.example.yaml`: class-first example.
- Tests: `tests/test_categories.py` (119 passing) + `test_intake.py` defaults/round-trip.
- Model + resolver only — exposure behavior comes in F17.01/F26.

## 2026-09-07 15:50:00 [AI]

F45: intake-store split (system `config.yaml` vs mutable `intake.yaml`).

- `app/intake.py` (new): `IntakeSettings` (`sources`, `gatherers`, `category_symlinks`) + `load()` (path+mtime-cached, missing→defaults) + `save()` (atomic temp+rename). The single place the program writes intake data.
- `app/config.py`: dropped `sources`/`gatherers`; added `intake_file: str = "intake.yaml"`.
- `app/registry.py`: `load_sources()`/`source_priority()` now read `intake.load()`.
- `intake.example.yaml` (new, tracked) + `config.example.yaml` slimmed; `.gitignore` + `docker-compose.yml` mount `intake.yaml`.
- Tests: `tests/test_intake.py` (114 passing) + `conftest.py` isolates `settings.intake_file`; `test_registry_load_sources`/`test_source_priority` use a temp `intake.yaml`.
- Docs: AGENTS.md (config split), README.md, schema/models + GATHERER_CONTRACT wording (`config.yaml`→`intake.yaml`).
- Manual migration: move `sources`/`gatherers` from your `config.yaml` into `intake.yaml`.

## 2026-09-07 15:25:00 [AI]

F32: per-source default location.

- `app/schema.py`: `SourceConfig.default_location: str | None = None` (optional, per-source only — no gatherer default).
- `app/sieve/sieve.py`: `_merge_default_location()` fills missing/blank `location` (before hashing, so it participates in change detection); `CONTRACT_VERSION` 1→2.
- `app/gatherers/elfsight/gatherer.py`: `CONTRACT_VERSION` 1→2 (re-affirm; no logic change).
- Docs: `GATHERER_CONTRACT.md` and `SIEVE_CONTRACT.md` → v2; `config.example.yaml` documents `default_location`.
- Tests: `tests/test_default_location.py` (110 passing) + `test_source_config_fields_match_doc` updated. No separate config contract (decision).

## 2026-09-07 15:10:00 [AI]

F34 + F34.01: Decisionmaker Contract (versioned + test-enforced).

- `docs/DECISIONMAKER_CONTRACT.md` (new, Version: 1) — `apply()` signature, report shape, persistence rules, the `ScrapedEvent → Event` mapping table, `last_seen_at`/`last_fetched_at` stamping + stale detection, and invariants (no commit, deterministic, trusts the sieve, pass-through policy).
- `app/decisionmaker/decisionmaker.py`: `# Contract: Decisionmaker v1` + `CONTRACT_VERSION = 1`.
- `tests/test_contract_decisionmaker.py` (new, 105 passing) — version, report shape, full-field mapping, update-path idempotency.
- `docs/GATHERER_CONTRACT.md`: deduped the old "What the Sieve adds"/"What the Decisionmaker persists" sections into a short "Downstream stages" pointer.

## 2026-09-07 14:55:00 [AI]

F33.03: split contract tests per stage.

- `tests/contract_helpers.py` (new) — shared `read_contract_version()` + `DOCS`.
- `tests/test_contract_sieve.py` and `tests/test_contract_gatherer.py` (new) — the tests moved out of the deleted `tests/test_contracts.py`, grouped by stage.
- AGENTS.md invariant updated to reference `tests/test_contract_*.py` + the shared helper.

## 2026-09-07 14:40:00 [AI]

F33.02: version-sign the Gatherer contract (per-gatherer).

- `docs/GATHERER_CONTRACT.md`: added `Version: 1`.
- `app/gatherers/elfsight/gatherer.py`: `# Contract: Gatherer v1` + `CONTRACT_VERSION = 1`. Each gatherer is stamped individually (they're written separately).
- `tests/test_contracts.py` (101 passing): gatherer field-consistency (SourceConfig/GathererConfig/ImageRef/ScrapedEvent/GathererResult `model_fields`) + a per-gatherer version check that discovers every `app/gatherers/<name>/gatherer.py` and asserts its `CONTRACT_VERSION` matches the doc.

## 2026-09-07 10:30:00 [AI]

F33 + F33.01: Sieve Contract (versioned + test-enforced).

- `docs/SIEVE_CONTRACT.md` (new) — source of truth for the sieve: inputs/outputs (`SieveResult`, `ClassifiedEvent`), classification rules, the `changed_fields` set, and invariants (read-only, idempotent, deterministic, only normalizes `default_categories`).
- `app/sieve/sieve.py`: `CONTRACT_VERSION = 1` + `# Contract: Sieve v1` comment.
- `tests/test_contracts.py` (new, 95 passing) — `_read_version()` helper, version-consistency, pydantic-shape/field-consistency, and read-only + idempotent `classify` checks.
- AGENTS.md: "Contracts are versioned + test-enforced" invariant. Pattern reused by F33.02 (gatherer), F34/F34.01 (decisionmaker).

## 2026-09-06 19:30:00 [AI]

Magic-number cleanup.

- `app/logging.py`: `LOG_TAIL_LINES = 200` (single source); `read_log_tail(n=LOG_TAIL_LINES)`; `/debug/logs` uses the default + an f-string label.
- `app/services/testrunner.py`: `COLLECT_TIMEOUT = 120`, `RUN_TIMEOUT = 300`.
- `app/gatherers/base.py`: `FETCH_TIMEOUT = 30.0`.

## 2026-09-06 19:30:00 [AI]

Event listing: default limit + future-first ordering.

- `app/services/events.py`: `DEFAULT_LIMIT = 500` (single source of truth); `query_events()` default changed 200→500 and orders by `start_at` descending (furthest future first, NULL last).
- `app/routers/events.py`: `/events` default limit now imports `DEFAULT_LIMIT` (no more hardcoded 200).
- Caching deferred by decision (single-digit-ms WAL read + serialization; multi-process invalidation not worth it yet).
- Tests: updated order-sensitive assertions in `test_events.py` + `test_default_limit` (89 passing).

## 2026-09-06 19:10:00 [AI]

F15: stale/removal detection (events deleted at the source).

- `app/models.py`: `Event.last_seen_at: datetime | None` (naive UTC). Schema change → wipe + re-ingest.
- `app/schema.py`: `SieveResult.unchanged_ids`; `app/sieve/sieve.py` populates it (keeps `unchanged` count).
- `app/decisionmaker/decisionmaker.py`: `apply()` computes `run_ts = utcnow()` and stamps `last_seen_at` on new/updated/unchanged events, sets `source.last_fetched_at = run_ts` (single source of truth), then detects stale events (`last_seen_at IS NULL OR != run_ts` for that source) and returns `removed` in the report.
- `app/ingest.py`: dropped the now-redundant `source.last_fetched_at = utcnow()` in `process_source`; `_print_report` + per-source summaries carry `removed`.
- `app/services/stats.py`: `stale_events()` (join Source; NULL or != last_fetched_at); `/debug/stale` HTML page + dashboard link; `/debug/ingest` table gains a `removed` column.
- Tests: `tests/test_stale.py` (88 passing) — unchanged_ids, last_seen_at on seen events, end-to-end removal, NULL migration case, `stale_events` service, and the `/debug/stale` route; updated 6 existing exact-report assertions to include `removed`.
- Detection only: stale events remain served by `/events` until F22 archives them.

## 2026-09-06 18:50:00 [AI]

F37.05: run the pytest suite from the browser.

- `app/services/testrunner.py`: `collect_tests()` / `run_tests(node_id)` shell out to `python -m pytest` in a subprocess (isolated from the server, same entrypoint as the CLI); `PROJECT_ROOT` pinned from `__file__`, output parsed/concatenated.
- `app/routers/tests.py` (registered in `app/admin.py`): `GET /debug/tests` lists collected tests (grouped by file in `<details>`) with a "run all" + per-test run buttons; `POST /debug/tests` runs and shows 🟢 passed / 🔴 failed (exit N) + output. IP+CSRF gated.
- `Dockerfile`: `COPY tests ./tests` + `pip install ".[dev]"` so the tests page works in-container.
- `app/web.py`: nav gains a `tests` link.
- Tests: `tests/test_testrunner.py` (82 passing) — collect parsing, run_tests command construction + output concat, route pass/fail rendering, CSRF rejection.

## 2026-09-06 18:30:00 [AI]

F37.04: trigger full ingest from the debug menu.

- `app/ingest.py`: extracted `_run(dry_run) -> (results, summaries)` as the single implementation; `run()` (CLI) and new `run_report()` (web) are thin wrappers over it — same code path as `python -m app.ingest`, no branching.
- `app/routers/ingest.py` (registered in `app/admin.py`): `GET/POST /debug/ingest` — dry-run checkbox (checked by default), IP+CSRF gated, renders a per-source counts table (status emoji, new/updated/unchanged/inserted, error message).
- `app/web.py`: nav gains an `ingest` link.
- Tests: `tests/test_ingest_route.py` (77 passing) — `run_report` summaries, dry-run vs commit, failing-source error summary, CSRF rejection, and a test locking the shared `_run()` path (`run`/`run_report` both route through it).

## 2026-09-06 18:10:00 [AI]

F37.03: database wipe behind two-layer verification.

- `app/db.py`: `wipe_db()` deletes Event then Source rows (FK order) in one commit, returns `(events, sources)`; schema untouched.
- `app/services/status.py`: added `reset_status()` (writes `{}`).
- `app/services/wipe.py`: `wipe_all()` = `wipe_db()` + `reset_status()` + delete `data/last_ingest.json`.
- `app/routers/wipe.py` (registered in `app/admin.py`): `GET /debug/wipe` (red "delete database" button) → `POST` `stage=arm` (reveals the sentence) → `POST` `stage=confirm` (must type "I understand the data will be permanently deleted" in full). IP-gated + CSRF-checked.
- `app/routers/debug.py`: "danger zone" link on the dashboard.
- Tests: `tests/test_wipe.py` (71 passing) — `wipe_db` empties tables + schema survives, `wipe_all` resets status/last-ingest, two-layer route flow + wrong-sentence/csrf rejection, and a resume test (wipe → server still serves 200/empty → re-ingest repopulates).
- AGENTS.md updated (wipe invariant + admin endpoint).

## 2026-09-06 17:45:00 [AI]

F37.02: browser log view (rotating file + /debug/logs tail).

- `app/config.py`: new `log_file` / `log_max_bytes` / `log_backup_count` settings (env `RIPCALE_*`); `log_file` relative paths resolve against `data_dir`, empty → `{data_dir}/ripcale.log`.
- `app/logging.py`: `setup_logging()` now attaches a `RotatingFileHandler` (delay=True) to the root logger in addition to the console stream — idempotent (file handler keyed on `RotatingFileHandler`, stream on exact `StreamHandler` type). Added `log_path()` and `read_log_tail(n=200)` — a constant-time backward tail (seek-to-end, block reads, drop the leading partial line); decodes with `errors="replace"`.
- `app/routers/debug.py`: IP-gated `GET /debug/logs` renders the last 200 lines (escaped) or "no log entries yet".
- `app/web.py`: nav gains a `logs` link.
- Tests: `tests/test_logging.py` (66 passing) — tail correctness (exact last-N, missing/empty, fewer-than-N, no trailing newline, >8 KB block boundary), setup idempotency, rotation caps backups, and the route render.
- Known limitation (documented in AGENTS.md): rotation is not multi-process-safe; disk stays capped.

## 2026-09-06 17:20:00 [AI]

F37.01: per-source run status + dashboard lights.

- `app/services/status.py`: status store at `data/status.json` (`read_status`/`record_status`/`record_run` + `source_status`/`gatherer_rollup`). Outcomes `ok`/`warning`/`error`; a 0-event run is recorded as `warning`.
- `app/ingest.py`: each source run records its outcome (batch ingest and the pipeline playground both go through the same path).
- `app/routers/debug.py`: `/debug` renders collapsible per-gatherer sections with 🟢/🟡/🔴/⚪ lights (rolled up per gatherer by highest severity) + raw status.
- `app/routers/pipeline.py`: gather/sieve/decide record their per-source outcome.
- Tests: `tests/test_status.py` (56 passing; conftest tmp `data_dir` keeps the real `data/` clean). Verified live: elfsight 🟢, 505 events.
- AGENTS.md updated (status.py key file + status invariant).

## 2026-09-06 16:17:21 [AI]

F37: gatherer error handling + logging.

- `app/logging.py`: `setup_logging()` (basicConfig, INFO, clear format); called from `main()` of `public`, `admin`, `ingest`, `debug`.
- `app/ingest.py`: `run()` wraps each source in try/except — logs (`logger.exception`), rolls back the session, records `{"name", "error"}` in the summary (feeds `last_ingest.json`), and continues to the next source.
- `app/routers/pipeline.py`: `_available_gatherers()` logs import failures (was a silent `continue`); gather/sieve/decide POST handlers catch exceptions and render a clear error page (new `_error_page` helper) instead of a bare 500.
- Tests: `tests/test_error_handling.py` — a failing source doesn't crash `ingest.run()` (others still process, error recorded) and a broken gatherer is skipped by discovery (51 passing).

## 2026-09-06 01:14:29 [AI]

F24: pipeline stages into their own directories.

- `app/sources/` → `app/gatherers/`; `sources/elfsight/module.py` → `gatherers/elfsight/gatherer.py`.
- `app/sieve.py` → `app/sieve/sieve.py` + `app/sieve/__init__.py` (re-exports `classify`).
- `app/decisionmaker.py` → `app/decisionmaker/decisionmaker.py` + `__init__.py` (re-exports `apply`).
- Updated import paths: `registry.load_gatherer()` → `app.gatherers.{name}.gatherer`; `pipeline._available_gatherers()` → `app.gatherers`; gatherer `base`/`elfsight`/`__main__` imports; 5 test files (`app.gatherers.elfsight.gatherer`).
- Re-export convention keeps `from app.sieve import classify` / `from app.decisionmaker import apply` working unchanged.
- Docs: AGENTS.md (Key files list), GATHERER_CONTRACT.md, README.md paths; TODO.md F24 → Done.
- Pure refactor — no schema change, no wipe. 49 tests passing; boot + `python -m app.gatherers.elfsight` verified.

## 2026-09-05 23:26:34 [AI]

F39 + F39.01: unified "gatherer" terminology + the configuration contract.

- Renamed "module"/"kind"/"adapter" → "gatherer" across config, code, docs, and tests:
  - `SourceConfig.gatherer` (was `.module`), `Source.gatherer` (was `.kind`), `ModuleResult` → `GathererResult`, `load_module()` → `load_gatherer()`, `_available_modules()` → `_available_gatherers()`.
  - Config: `sources[].gatherer:` (was `module:`); `gatherers:` block unchanged.
  - Docstrings/comments "source module"/"source adapter" → "gatherer".
- Filenames/paths intentionally left (`app/sources/<name>/module.py`, `import_module`, `iter_modules`) — that's F24 (directory refactor).
- `docs/GATHERER_CONTRACT.md`: added a "Configuration" section — the stable interface (`SourceConfig` uniform fields + `GathererConfig` defaults), resolution order (`source > gatherer default > 0`), and the determinism/uniformity principle.
- Schema change: `Source.gatherer` (was `kind`) → wiped + re-ingested (505 events; `source.gatherer` = "elfsight").
- 49 tests passing; AGENTS/README/TODO updated.

## 2026-09-05 22:59:51 [AI]

F31.01 revision: priority is config-only + a nullable event override (no resolved column).

- Reverted `Source.priority` (was a resolved/stamped column) and `_effective_priority()` in `ingest._ensure_source`.
- `Event.priority: int | None = None` — the single per-event priority column; `NULL` = "inherit from source".
- Priority is resolved config-side by `registry.source_priority(cfg)` = `cfg.priority ?? gatherers[module].priority ?? 0` (event-level override layers on top later, in F14/F28).
- No `ScrapedEvent.priority` (priority isn't gatherer output); `stats.sources()` no longer exposes priority.
- Inheritance model: `event.priority ?? source.priority ?? gatherer.priority ?? 0` — avoids denormalization/drift.
- Tests: replaced the two ingest-priority tests with `test_source_priority` (49 passing). Wiped + re-ingested (priority column now on `event`, nullable, all NULL).

## 2026-09-05 22:37:06 [AI]

F31.01 (source priority) + F31.02 (recurrence overrides).

F31.01 — two-level source priority:
- `app/schema.py`: `GathererConfig` (extensible, `extra="allow"`, `priority: int = 0`) + `SourceConfig.priority: int | None = None` (None = inherit).
- `app/config.py`: `Settings.gatherers: dict[str, GathererConfig]`.
- `app/models.py`: `Source.priority: int = 0` (stores the resolved value).
- `app/ingest.py`: `_effective_priority()` (source > gatherer default > 0); `_ensure_source` persists + syncs it.
- `config.yaml`/`config.example.yaml`: `gatherers:` block (keyed by module) + per-source `priority`, with inheritance documented.
- `stats.sources()` exposes `priority`.

F31.02 — recurrence overrides:
- `app/schema.py`: `ScrapedEvent.recurrence_id: datetime | None` + `exdates: list[datetime]`; `dump_exdates`/`load_exdates`.
- `app/identity.py`: `stable_id` appends `:recurrence_id` (backward-compatible); `content_hash` includes `exdates` (not `recurrence_id` — identity).
- `app/sieve.py`: `exdates` in `_CHANGED_FIELDS` (list-vs-JSON diff).
- `app/decisionmaker.py`: maps `recurrence_id` + `exdates`.
- `app/serializers.py`: `extendedProps.exdates` + `recurrence_id`.
- `app/services/ics.py`: emits `EXDATE` (master) + `RECURRENCE-ID` (override).
- Docs: GATHERER_CONTRACT.md (recurrence_id/exdates in the contract; series/overrides now implemented), AGENTS.md, TODO.md (F31.01/F31.02 → Done).
- Tests: priority resolution/persistence, override identity, exdates hash/change, ICS EXDATE/RECURRENCE-ID, serializer (50 passing).

## 2026-09-05 22:07:49 [AI]

F31: recurrence field in the Gatherer contract + groundwork columns.

- `app/schema.py`: `ScrapedEvent.rrule: str | None` (RFC 5545 RRULE value; no `RRULE:` prefix, no `DTSTART` — first occurrence is `start_at`).
- `app/models.py`: `Event.rrule` is now the active contract field (no longer "reserved"); added groundwork columns `recurrence_id` (override DTSTART), `exdates` (JSON of cancelled occurrence DTSTARTs), `redirect_to_id` (event redirect/symlink, indexed).
- Wired `rrule` through `content_hash`, `_CHANGED_FIELDS`, decisionmaker (insert/update), JSON `extendedProps.rrule`, and ICS (`RRULE` via `vRecur.from_ical`). `stats.event_dump` now shows the new columns.
- No Elfsight→RRULE translator (live data has 0 recurring events; Google Calendar gatherer F25 will be the first real recurrence source).
- Docs: GATHERER_CONTRACT.md (rrule field + Recurrence/relationships sections; recurrence gap removed), AGENTS.md (43 tests, recurrence invariant), TODO.md (F31 → Done).
- Tests: content_hash/sieve/ics/events rrule coverage + new-column defaults (43 passing). Wiped + re-ingested DB (columns present).

## 2026-09-05 20:42:38 [AI]

Context hygiene + pre-commit prep (no code changes).

- Applied the F## ticket-numbering convention to `TODO.md` (F01-F36; child syntax `F##.NN` documented in the header).
- Source-URL policy change: the Elfsight widget id is now treated as public — tests/fixture were anonymized then re-included, and `config.example.yaml` ships the real Studio Two Three boot URL as starter data. Private/secret sources still belong in gitignored `config.yaml`.
- Pre-commit secret audit: no keys/tokens/credentials in tracked files; the Elfsight fixture is a frozen snapshot of real public data, so tests never hit the network and won't break when the live source changes.
- Updated AGENTS.md (test count 39, `ImageRef`/multi-image invariants, source-URL wording) and README.md Configuration wording.

## 2026-09-05 19:11:23 [AI]

F35: multiple ordered images per event (gallery).

- `app/schema.py`: added `ImageRef` (`url`, `alt`, `source_url`) + `dump_images()`/`load_images()`; `ScrapedEvent.images: list[ImageRef]` replaces `image_url`.
- `app/models.py`: `Event.images` JSON text column (drop `image_url`).
- `app/identity.py`: `content_hash` now hashes the ordered `images`.
- `app/sieve.py`: `_CHANGED_FIELDS` `image_url` -> `images`; `_changed_fields` diff compares `load_images(old.images)`.
- `app/decisionmaker.py`: persists `dump_images(e.images)`.
- `app/sources/elfsight/module.py`: `_images()` emits the ordered gallery (alt carried; falls back to coverImage).
- `app/serializers.py` / `services/stats.py`: expose `images` (list of `{url, alt, source_url}`); `services/ics.py` emits one `ATTACH` per image + `X-RVA-IMAGE` = `images[0].url`.
- Docs: GATHERER_CONTRACT.md (Images section rewritten for ordered gallery, primary = images[0]), README.md.
- Tests: multi-image ICS, content_hash images, sieve images-change (39 passing). Wiped + re-ingested DB (505 events; alt captured when present).

## 2026-09-05 17:08:29 [AI]

Pipeline playground `decide` dry-run toggle.

- `app/routers/pipeline.py`: `_form()` gained an `extra` slot; the decide page now renders a dry-run checkbox (checked by default) so the safe "preview without writing" path is the default; `decide_run()` branches on `dry_run` (dry-run shows the diff + full result and commits nothing; unchecking commits).
- Test: `tests/test_pipeline_playground.py` — dry-run leaves the DB unchanged, commit writes events (36 passing).
- Live-verified: checkbox renders + checked; dry-run POST -> 200 "nothing written" and event count unchanged.

## 2026-09-05 16:40:05 [AI]

Docker-aware admin access (auto-detect + bridge-subnet allowlist).

- `app/security.py`: added `in_docker()` (auto-detects via `/.dockerenv`, overridable with `RIPCALE_IN_DOCKER`) and `DOCKER_BRIDGE_CIDR = "172.16.0.0/12"`. `is_debug_allowed()` now accepts the Docker bridge subnet when running inside a container.
- `app/admin.py`: binds `0.0.0.0` when in Docker (the published port DNATs to the container's eth0, so a `127.0.0.1` bind is unreachable), else `admin_host` (loopback).
- Rationale: outside Docker the admin stays loopback-only; inside Docker it works via the loopback-published port (`127.0.0.1:8082:8082`), where the bridge gateway is the only peer — so accepting `172.16.0.0/12` is safe.
- Tests: `test_is_debug_allowed_docker` + `test_in_docker_detection`; 35 passing. Docs updated (config.example.yaml, README).

## 2026-09-05 16:25:59

Just as a note, going forward I'd like to use HikerAPI for instagram unless better alternatives exist. Not only does it allow me to not have to register an account with instagram, but it looks like it does everything I need! (i.e. watch and pay attention to specific instagram pages)

## 2026-09-05 16:04:20 [AI]

Split the app into two listeners: public (read-only) and admin (interactive).

- `app/public.py`: read-only API (`/events`, `/events/{id}`, `/feed.ics`, `/events/{id}/ics`, `/healthz`) with CORS; binds `public_host`/`public_port` (0.0.0.0:8081).
- `app/admin.py`: debug + pipeline playground (`/debug*`, incl. the write `decide`); no CORS/healthz; binds `admin_host`/`admin_port` (127.0.0.1:8082, loopback-only).
- `app/main.py` repurposed into a local-dev launcher (spawns both as subprocesses); Docker runs the two entrypoints directly.
- Config: `host`/`port` -> `public_host`/`public_port`, added `admin_host`/`admin_port`. `config.yaml`, `config.example.yaml`, `.env.example` updated.
- `docker-compose.yml`: two services (`public` on 0.0.0.0:8081, `admin` on 127.0.0.1:8082) sharing `data` + `config.yaml`. `Dockerfile`: CMD -> `app.public`, EXPOSE 8081.
- Rationale: the interactive/admin surface is loopback-bound at the network layer, so the debug IP allowlist no longer needs the Docker-subnet widening (which would have been equivalent to "any interface").
- Tests updated (`from app.public import app` / `from app.admin import app`); 33 passing.
- Live-verified: public :8081 (healthz 200, /events 200), admin :8082 (/debug + /debug/pipeline 200), /debug correctly 404 on :8081.

## 2026-09-05 15:31:48 [AI]

Debug tooling + pipeline playground + full documentation + end-to-end tests.

- `app/security.py`: IP allowlist (`is_debug_allowed`; loopback always, else `debug_allowed_cidrs`) and CSRF token (`debug_token` or auto-generated). `form_data()` parses `application/x-www-form-urlencoded` from `request.body` (Robyn does not populate `request.form_data` on the real server — found via a scratch probe).
- `app/services/stats.py`: non-secret aggregates (overview, per-source, single-event dump, last-ingest read).
- `app/web.py`: dependency-free HTML helpers (page shell, escape, table, json-pre).
- `app/routers/debug.py`: `GET /debug` (static HTML dashboard), `/debug/stats`, `/debug/sources`, `/debug/events/{id}` — all IP-gated, non-secret.
- `app/routers/pipeline.py`: `/debug/pipeline` home + `gather`/`sieve`/`decide` (GET form + POST handler), IP-gated + CSRF. Gather/Sieve render the complete, untruncated result (incl. `raw`).
- `app/debug.py`: CLI (`python -m app.debug [stats|sources|events --id]`).
- `app/ingest.py`: writes `data/last_ingest.json` after each non-dry run.
- Config: `debug_allowed_cidrs`, `debug_token` (config.yaml + `.env`).
- Tests: `test_pipeline.py` (full end-to-end + change detection + registry) and `test_debug.py` (allowlist, CSRF, stats, routes); 33 passing.
- Documentation: every module now has a docstring (with call-chain), `#region` sections, and function docstrings.
- Live-verified: `/debug` (200 text/html), `/debug/stats`, gather/sieve POST with CSRF (403 on wrong token), CLI stats/sources.

## 2026-09-05 14:37:02 [AI]

Milestone 5: ICS feeds (RFC 5545 subscription).

- Added `icalendar` dep. `app/services/ics.py`: `event_to_vevent()` + `events_to_ics()`.
  - Standard properties: `UID` (stable id), `SUMMARY`, `DTSTART`/`DTEND` (UTC `Z`; all-day -> `VALUE=DATE`), `DTSTAMP`, `DESCRIPTION` (HTML-stripped text), `X-ALT-DESC;FMTTYPE=text/html` (HTML), `LOCATION`, `URL`, `ATTACH` (image URI), `CATEGORIES`.
  - Custom: `X-RVA-SOURCE`, `X-RVA-TIMEZONE`, `X-RVA-IMAGE`.
- `app/routers/feeds.py`: `GET /feed.ics` (full feed, optional `?tag=` filter), `GET /events/:id/ics` (single event, 404 if absent).
- URL deviation from plan: Robyn's router cannot express `:param.suffix` — `/feed/:tag.ics` becomes a single param named `tag.ics` and `/events/:id` + `/events/:id.ics` are the same route shape. So tagged feed uses `?tag=` and single-event ICS is `/events/{id}/ics`.
- `app/services/events.py`: extracted shared `source_names()`; `query_events(limit=None)` returns all (used by feeds).
- Fixed: `icalendar` does not escape newlines in `X-ALT-DESC` (throws "unescaped new line"); sanitize HTML newlines to spaces (18 real events had literal `\n`).
- Tests: 23 passing; live `/feed.ics` -> 200 `text/calendar`, 505 VEVENTs, parses cleanly.

## 2026-09-05 12:07:04 [AI]

Milestone 4: JSON read API (FullCalendar-compatible).

- `GET /events` -> FullCalendar `event-parsing` array (`id`, `title`, `start`/`end` as UTC ISO-8601, `allDay`, `url`, `extendedProps` for description/location/categories/image_url/timezone/source). Filters: `start`/`end` (ISO range, URL-encoded), `category` (exact tag), `limit` (default 200). Ordered by `start_at`.
- `GET /events/:id` -> single event, 404 if absent.
- `app/serializers.py`: `Event -> FullCalendar dict`; naive-UTC -> `...Z`, all-day -> date-only strings.
- `app/services/events.py`: `query_events()` / `get_event()` (pure, unit-testable; `coalesce(end_at, start_at)` for overlap queries).
- `app/routers/events.py`: thin Robyn handlers; `unquote_plus` on query values (Robyn does not URL-decode `query_params`).
- `app/timeutil.py`: added `parse_iso_utc()`.
- `app/sieve.py`: now merges the source's `default_categories` into each event before hashing (fixes a gap where source defaults like `art` were never applied; re-ingest correctly flagged all 505 as `changed: categories`).
- CORS via Robyn `ALLOW_CORS`, origins from `cors_origins` config (default `*`).
- Tests use Robyn `TestClient`; 18 passing.

## 2026-09-05 11:51:21 [AI]

Config/data split: monolithic `config.yaml`, secrets in `.env`, wipeable `./data`.

- `config.yaml` (gitignored) now holds all non-secret config: `host`, `port`, `data_dir`, `database_url`, and the `sources` list. `config.example.yaml` is the tracked template.
- `.env` (gitignored) holds API keys + `RIPCALE_*` overrides only; `.env`/env-vars override `config.yaml` (pydantic-settings source order: env > dotenv > yaml > defaults).
- `app/config.py`: `Settings` gained `sources: list[SourceConfig]`; added `YamlConfigSettingsSource` via `settings_customise_sources` (pydantic-settings does not auto-enable `yaml_file`).
- `app/registry.py`: `load_sources()` now returns `settings.sources` (no more `data/sources.yaml`, no manual YAML parsing).
- `./data/` now holds only generated data (SQLite DB) and is safe to wipe; `init_db()` recreates it automatically.
- `docker-compose.yml`: added `./config.yaml:/app/config.yaml:ro` mount.
- Verified: missing `config.yaml` -> boots on defaults (empty sources); `.env` port override beats `config.yaml`; fresh ingest -> 505 inserted -> re-run 505 unchanged; 12 tests green.

## 2026-09-05 11:11:22 [AI]

Milestone 3: ingest pipeline (gather -> sieve -> decide -> store).

- Pipeline: source modules massaging data -> `Sieve` (read-only change detection vs DB) -> `Decisionmaker` (policy + persist). Change detection split from persistence; dry-run inspectable before any write.
- `app/schema.py`: `SourceConfig`, `ScrapedEvent`, `ModuleResult`, `ClassifiedEvent`, `SieveResult` contracts.
- `app/identity.py`: `stable_id()` (sha256 of source+uid, title+start fallback) and `content_hash()` (canonical hash over mutable fields).
- `app/timeutil.py`: `to_utc_naive()`. Convention: all stored datetimes are naive UTC; IANA name kept in `Event.timezone`.
- `app/models.py`: added `content_hash` column (indexed); `utcnow()` now naive UTC.
- `app/registry.py`: loads `data/sources.yaml` -> `SourceConfig`s; `load_module()` imports `app.sources.<name>.module`.
- `app/sources/elfsight/`: generic Elfsight event-calendar adapter. Resolves `eventType`/`location` ID arrays via lookups; parses datetimes (timezone-aware -> UTC), images, action links, recurrence retained in `raw`. `python -m app.sources.elfsight` prints `ModuleResult` JSON standalone.
- `app/sieve.py`: `classify()` buckets new/updated/unchanged; `_relevance()` is an intentional pass-through placeholder where drop-past (and future relevance rules) will land.
- `app/decisionmaker.py`: `apply()` persists new + updates (bumps `updated_at` only on change); stub for future cross-source heuristics.
- `app/ingest.py`: `--dry-run` (sieve only) and full run; ensures `Source` row; prints per-source report.
- `data/sources.yaml`: Studio Two Three -> Elfsight boot endpoint (505 events).
- Tests: identity, elfsight, sieve, decisionmaker, ingest idempotency (12 passing).
- Verified live: dry-run 505 new -> ingest 505 inserted -> re-run 505 unchanged.

## 2026-09-05 10:07:11 [AI]

Milestone 2: data layer.

- Added `sqlmodel` (SQLAlchemy 2.0) to deps; verified SQLite WAL mode via `PRAGMA journal_mode=WAL` on connect.
- `app/models.py`: `Source` and `Event` SQLModel tables. `Event.id` is a stable string PK (UID-derived), with title/description/location/geo/url/image_url/start_at/end_at/timezone/all_day/rrule/categories + timestamps.
- `app/db.py`: engine, `init_db()` (creates `data/ripcale.db` + tables), `get_session()`.
- `app/config.py`: added optional `database_url` (defaults to `sqlite:///{data_dir}/ripcale.db`).
- `app/main.py`: calls `init_db()` on startup.
- `data/sources.yaml`: gitignored secret source list (example entry only).
- `tests/test_db.py`: create/query + defaults (2 passing).

## 2026-09-05 09:55:00 [AI]

Project rename: the backend now lives in `ripcale-backend/` and is called **ripcale** going forward.

- Moved the backend (app, tests, pyproject, Docker bits, config) into `ripcale-backend/`.
- Renamed package `rva-rip-backend` -> `ripcale`, healthz `service` -> `ripcale`, env prefix `RVA_` -> `RIPCALE_`, container name -> `ripcale-backend`.
- Verified `GET /healthz` -> `{"status":"ok","service":"ripcale","version":"0.1.0"}` (HTTP 200) after the move.

## 2026-09-05 09:50:03 [AI]

Milestone 1: backend scaffold.

- Locked stack: Robyn (Rust-runtime Python web framework) + SQLModel/SQLAlchemy/SQLite + `icalendar`/`recurring-ical-events` + pydantic-settings + APScheduler + Docker.
- Created scaffold: `pyproject.toml`, `app/` package (`main.py`, `config.py`), `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`.
- `GET /healthz` returns `{"status":"ok","service":"rva.rip-aggregator","version":"0.1.0"}`.
- Robyn 0.88.0 verified on Python 3.14 (prebuilt cp314 wheel); serves on the Actix (Rust) runtime, auto OpenAPI at `/docs`.
- Default bind port moved 8080 -> 8081 (8080 is occupied by syncthing on this machine); configurable via `RVA_PORT`.
- Note: Docker daemon not running in this environment, so the container build is written but not yet verified.
