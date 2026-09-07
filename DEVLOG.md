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
