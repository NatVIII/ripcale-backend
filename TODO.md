# TODO

Kanban board. Move a card by moving its line between sections.

Each Item has a ticket number (F##). Any child tickets which are necessary for accomplishing larger matters are denoted as children by using the larger feature's ticket as their initial followed by a period and then a number. Numbers are incrementing for tickets in a way that does not overlap, new ticket numbers are simply the new lowest value for what could be in that location. Each section has atleast two digits, so for example, the first ticket would be F01, the second would be F02, the first child of the second ticket would be F02.01, etc. 

## Backlog

- [ ] F37 - Confirm sensible defaults that mean that when errors occur with gatherers that those errors are caught and spewed into error logs; instead of just breaking without any kind of message. 
- [ ] F37.01 Perhaps feature a field on /debug which shows whether the last performance of each gatherer with a colored light emoji worked. 
- [ ] F15 - Stale/removal detection (events deleted at the source; needs `last_seen_at`)
- [ ] F33 - Write the Sieve Contract
- [ ] F34 - Write the Decisionmaker Contract
- [ ] F32 - Default location: configurable default location applied to events with a missing/blank `location` (config field; normalized in one shared place).
- [ ] F26 - Category to category symlinks (so that internal categories can be saved and referenced, but still be a part of real and exposed external categories)
- [ ] F17 - Category → color mapping (Elfsight `categoryColor` not yet stored). Configured inside of the config.yaml, assigning colors to different categories. 
- [ ] F17.01 There should also be a way to specify which categories are the "true" categories, which are meant to be publicly exposed as that kind for sortation (in truth a very small list of "true" categories) from the internal symlinked categories only kept so that data isn't being deleted from the original source.
- [ ] F29 - Category and symlink mapping on the /debug page
- [ ] F13 - Relevance/expiry filter in `sieve._relevance()`: drop events older than X days and farther than Y days in the future (currently pass-through). Single config + single shared expiry logic (with F22).
- [ ] F22 - DB trash handling / garbage collection: archive (soft-delete) events older than X days instead of deleting them - keep them saved for future reference, but exclude them from the normal read path. Shares the same expiry config + logic as F13 (one implementation, no duplicated handlers).
- [ ] F28 - Event Editor: Edit events on the backend using the /debug API. Keep just regular HTML, no Javascript for this
- [ ] F25 - Gatherer: Google Calendar Gatherer
- [ ] F21 - Gatherer: Instagram source (research HikerAPI - see DEVLOG note)
- [ ] F18 - Image hosting (v1 links out; self-hosting deferred by design)
- [ ] F11 - Scheduler: automatic ingest (APScheduler / cron) - nothing polls yet
- [ ] F12 - Recurrence expansion (recurring Elfsight events; fields kept in `raw`)
- [ ] F14 - Decisionmaker heuristics (cross-source dedup, manual-over-scraped priority)
- [ ] F19 - Frontend (rva.rip - FullCalendar consuming `/events` + `/feed.ics`)
- [ ] F20 - Community submission + approval system (deferred by design)
- [ ] F23 - Backup mechanism: in-app scheduled snapshots of the SQLite DB to a configurable location (e.g. a `backup_dir` config field), with a retention policy. Part of the internal workings (not an external cron).
- [ ] F36 - Implement Telegram communication and decisionmaking in the Decisionmaker. I want a telegram bot to be able to help me be notified of possible event conflicts and help choose
- [ ] F16 - `/sources` public endpoint (deferred)

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

## Deleted
- [ ] F30 - Deleted Event