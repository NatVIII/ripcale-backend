# TODO

Kanban board. Move a card by moving its line between sections.

Each Item has a ticket number (F##). Any child tickets which are necessary for accomplishing larger matters are denoted as children by using the larger feature's ticket as their initial followed by a period and then a number. Numbers are incrementing for tickets in a way that does not overlap, new ticket numbers are simply the new lowest value for what could be in that location. Each section has atleast two digits, so for example, the first ticket would be F01, the second would be F02, the first child of the second ticket would be F02.01, etc. 

## Backlog

- [ ] F50.05 - Build a debug tool that implements this entire logic pipeline using any custom combination onto a gatherer, with a dry-run checkbox that's true by default and displaying of results, so that one can either test to make sure their string will work or be able to run one time commands to implement this.
- [ ] F47 - In case it does become necessary to transition to a new tag altogether, mass movements of tags can occur programatically and through the interface. This isn't simply symlinking, but using some kind of parameters to trigger large changes to sections of the database.
- [ ] F48 - PGP Authentication for the frontend; we need to start verifying the frontend and making sure that the person using it is actually the intended user; and PGP is like the gold standard in security, no? I'd like to make an interface where a user can log in, in order to verify authentication. I really don't know how this can be done in a truly secure fashion, part of why I'd still like this to remain behind the admin only port for now no matter what at this time, but I'd like to start laying the groundwork for my own knowledge of truly secure authentication and it's implementation, by working with you (我亲爱的LLM)
- [ ] F17 - Category → color mapping (Elfsight `categoryColor` not yet stored). Configured inside of the config.yaml, assigning colors to different categories. 
- [ ] F17.01 There should also be a way to specify which categories are the "true" categories, which are meant to be publicly exposed as that kind for sortation (in truth a very small list of "true" categories) from the internal symlinked categories only kept so that data isn't being deleted from the original source.
- [ ] F29 - Category and symlink mapping on the /debug page
- [ ] F13 - Relevance/expiry filter in `sieve._relevance()`: drop events older than X days and farther than Y days in the future (currently pass-through). Single config + single shared expiry logic (with F22).
- [ ] F22 - DB trash handling / garbage collection: archive (soft-delete) events older than X days instead of deleting them - keep them saved for future reference, but exclude them from the normal read path. Shares the same expiry config + logic as F13 (one implementation, no duplicated handlers).
- [ ] F28 - Event Editor: Edit events on the backend using the /debug API. Keep just regular HTML, no Javascript for this
- [ ] F44 - Find a preferred way to set up an automatic build pipeline; where development builds can be compiled into releases on github (using the command line preferably because I like it, or without having to create releases and instead just being able to trigger a re-grab and re-build using my terminal with the server) and on release an automatic deployment to a server can occur. Selfishly, this is so that I can build on my PC and then deploy on my testing server.
- [ ] F25 - Gatherer: Google Calendar Gatherer
- [ ] F21 - Gatherer: Instagram source (research HikerAPI - see DEVLOG note)
- [ ] F40 - Post-Sieve Feature, FITB with image OCR. The Instagram 
- [ ] F18 - Image hosting (v1 links out; self-hosting deferred by design)
- [ ] F11 - Scheduler: automatic ingest (APScheduler / cron) - nothing polls yet
- [ ] F12 - Recurrence expansion (recurring Elfsight events; fields kept in `raw`)
- [ ] F14 - Decisionmaker heuristics (cross-source dedup, manual-over-scraped priority)
- [ ] F19 - Frontend (rva.rip - FullCalendar consuming `/events` + `/feed.ics`)
- [ ] F20 - Community submission + approval system (deferred by design)
- [ ] F23 - Backup mechanism: in-app scheduled snapshots of the SQLite DB to a configurable location (e.g. a `backup_dir` config field), with a retention policy. Part of the internal workings (not an external cron).
- [ ] F16 - `/sources` public endpoint (deferred)
- [ ] F41 - Convert tests to CI/CD Pipeline that automatically triggers on each push to git (Codeberg, Github, Gittea?).
- [ ] F36 - Implement decisionmaking page and logic. I want a telegram bot to be able to help me be notified of possible event conflicts and help choose in the future, so this should be done via some kind of API communication or something so that the same interface. We can't implement the telegram bot yet, so let's make the interface via code and then make a debug page that allows for this to take place.
- [ ] F43 - External API Contract

## In Progress

## Done

- [x] F01 - backend scaffold (2026-09-05)
- [x] F02 - data layer: SQLModel + SQLite/WAL (2026-09-05)
- [x] F03 - ingest pipeline: gather → sieve → decide → store (2026-09-05)
- [x] F04 - JSON API (FullCalendar event-parsing) (2026-09-05)
- [x] F05 - ICS feeds (RFC 5545) (2026-09-05)
- [x] F06 - Debug tooling: dashboard + CLI + pipeline playground (2026-09-05)
- [x] F07 - Public/admin two-listener split (2026-09-05)
- [x] F08 - Docker-aware admin access (auto-detect + bridge subnet) (2026-09-05)
- [x] F09 - Decide dry-run toggle (default dry-run) (2026-09-05)
- [x] F10 - AGENTS.md + TODO.md + DEVLOG split (2026-09-05)
- [x] F27 - Map out in plaintext the Gatherer→Sieve/Decisionmaker contract → docs/GATHERER_CONTRACT.md (2026-09-05)
- [x] F35 - Multiple ordered images per event (ImageRef gallery) → schema/models/pipeline + docs/GATHERER_CONTRACT.md (2026-09-05)
- [x] F31 - Gatherer contract: recurrence — added `rrule` to `ScrapedEvent` (→ `Event.rrule`) + full wiring; groundwork columns `recurrence_id`/`exdates`/`redirect_to_id` added (2026-09-05)
- [x] F31.01 - Config priority: `gatherers:` per-gatherer defaults + optional `sources[].priority` override (config-only, resolved via `registry.source_priority`); `Event.priority` nullable column (NULL = inherit) (2026-09-05)
- [x] F31.02 - Recurrence overrides: `recurrence_id` + `exdates` in the contract, override-aware `stable_id`, EXDATE/RECURRENCE-ID in ICS (2026-09-05)
- [x] F39 - Gatherer configuration contract: documented the stable config interface (`SourceConfig` + `GathererConfig`, uniform/deterministic) in docs/GATHERER_CONTRACT.md (2026-09-05)
- [x] F39.01 - Renamed "module"/"kind"/"adapter" → "gatherer" across config, code, docs, and tests (filenames untouched for F24) (2026-09-05)
- [x] F24 - Split the pipeline stages into their own directories: `app/gatherers/`, `app/sieve/`, `app/decisionmaker/` (2026-09-06)
- [x] F38 - /debug/pipeline discovers gatherers programmatically (already in place via `_available_gatherers()`) (2026-09-06)
- [x] F37 - Gatherer error handling: `app/logging.py` (`setup_logging`), per-source try/except + rollback in `ingest.run()`, clear error pages in the pipeline playground, import-failure logging (2026-09-06)
- [x] F37.01 - Per-source run status + dashboard lights: `app/services/status.py` (`data/status.json`, ok/warning/error, 0-events→warning), wired into `ingest.run()` + pipeline playground, `/debug` per-gatherer status lights (2026-09-06)
- [x] F37.02 - Browser log view: `RotatingFileHandler` to `data/ripcale.log` (shared by all entrypoints, config `log_file`/`log_max_bytes`/`log_backup_count`) + IP-gated `/debug/logs` with constant-time backward tail (2026-09-06)
- [x] F37.03 - Wipe Database: `/debug/wipe` two-layer verification (arm button → type sentence in full → confirm), CSRF+IP gated; `wipe_db()` (Event→Source) + `wipe_all()` (also resets status/last-ingest); schema survives + server resumes (2026-09-06)
- [x] F37.04 - Debug ingest trigger: `/debug/ingest` (dry-run checkbox, IP+CSRF) runs `ingest.run_report()` — same `_run()` core as `python -m app.ingest` (2026-09-06)
- [x] F37.05 - Tests page: `/debug/tests` runs pytest out-of-process (`app/services/testrunner.py` subprocess), run-all + per-test buttons, pass/fail + output; Docker image now ships `tests/` + `[dev]` extras (2026-09-06)
- [x] F15 - Stale/removal detection: `Event.last_seen_at` stamped per run, `SieveResult.unchanged_ids`, `apply()` reports `removed`, `stats.stale_events()` + `/debug/stale` listing (detect only; F22 archives) (2026-09-06)
- [x] F42 - Magic-number cleanup: `LOG_TAIL_LINES`, `COLLECT_TIMEOUT`/`RUN_TIMEOUT`, `FETCH_TIMEOUT` (2026-09-06)
- [x] F33 + F33.01 - Sieve Contract + versioning: `docs/SIEVE_CONTRACT.md` (Version: 1), `CONTRACT_VERSION = 1` in `app/sieve/sieve.py`, `tests/test_contracts.py` (version + pydantic-shape + invariant checks) (2026-09-07)
- [x] F33.02 - Gatherer contract versioning: `docs/GATHERER_CONTRACT.md` (Version: 1), per-gatherer `CONTRACT_VERSION` (elfsight), `tests/test_contracts.py` field-consistency + per-gatherer version discovery check (2026-09-07)
- [x] F33.03 - Split contract tests per stage: `tests/contract_helpers.py` (shared) + `tests/test_contract_sieve.py` + `tests/test_contract_gatherer.py` (2026-09-07)
- [x] F34 + F34.01 - Decisionmaker Contract + versioning: `docs/DECISIONMAKER_CONTRACT.md` (Version: 1), `CONTRACT_VERSION = 1` in `app/decisionmaker/decisionmaker.py`, `tests/test_contract_decisionmaker.py`; deduped downstream sections out of `GATHERER_CONTRACT.md` (2026-09-07)
- [x] F32 - Default location: optional per-source `SourceConfig.default_location` (no gatherer default), merged in the sieve (blank/missing → default, before hashing); gatherer + sieve contracts bumped to v2 (2026-09-07)
- [x] F45 - Intake-store split: `intake.yaml` (sources/gatherers/category_symlinks) + `app/intake.py` (`load`/`save`, mtime-cached, atomic), system `config.yaml` slimmed to system settings + `intake_file`; registry reads intake (2026-09-07)
- [x] F46 - Category classes: class-first `IntakeSettings.category_definitions` (`{class: [category]}`) + `app/services/categories.category_class()` (defaults to `intake`); model + resolver only (2026-09-07)
- [x] F49 - Coherence checks: `app/services/coherence.check()` (intake structure + gatherer existence + category consistency + config sanity), fail-safe "coherence" section on `/debug` (2026-09-07)
- [x] F26 - Category symlinks: read-time `resolve_categories`/`resolve_event_categories` wired into serializer/`?category=`/ICS + forward "symlink" column on `/debug` (external-only exposure) (2026-09-07)
- [x] F50 - Categorization rule engine: new `app/categorize/` stage (`CategoryRule`: `regex`/`assign`, string fields), `default_categories` unified into the rules engine, wired before the sieve; `docs/CATEGORIZE_CONTRACT.md` v1; sieve/gatherer contracts bumped to v3 (2026-09-07)
- [x] F50.01 - Gatherer-scope rules: `GathererConfig.rules`, applied first in `categorize.apply()` (gatherer → default_categories → source); CATEGORIZE_CONTRACT v2, GATHERER_CONTRACT v4 (2026-09-07)
- [x] F51 - Class:name category identity + slug normalization: `class:name` baked at ingest (part of content_hash), dynamic classes (only `intake` default), slugify `[a-z0-9-]` at the categorize gate, symlinks read-time `class:name → class:name`; CATEGORIZE_CONTRACT v3 (2026-09-07)
- [x] F50.02 - Global-scope rules: top-level `IntakeSettings.rules` applied to all events, prepended in `categorize.apply()` (global → gatherer → default_categories → source); CATEGORIZE_CONTRACT v4 (2026-09-07)
- [x] F50.03 - `assign` mode (satisfied by F50: implemented during `default_categories` unification — no separate work needed) (2026-09-07)
- [x] F50.04 - Single implementation (satisfied by design; added guard tests locking `default_categories` == `assign` rule and same-rule-across-scopes) (2026-09-07)

## Deleted
- [ ] F30 - Deleted Event