# ripcale — Architecture & Migration Spec

> The durable spec behind TODO tickets **F69–F76**. Written to survive a context
> reset: it captures the target architecture, the standard interfaces, the
> loop/queue model, and the phased migration plan.

## 1. Context & current state

ripcale is a calendar aggregator backend for rva.rip. It scrapes event sources
(elfsight widget, ICS feeds, Instagram via HikerAPI), normalizes them into a
common schema, and serves them as a FullCalendar JSON API + RFC 5545 ICS feeds.
It runs as HTTP listeners plus background workers, deployed via Docker
(poll-based pull deploy, non-root, SSRF-guarded, backups).

- **542 tests passing** at the start of this work.
- Two listeners today: `public` (read-only, `:8081`) and `admin` (R/W + debug,
  `:8082`).
- Pipeline: `gather → categorize → sieve → decisionmaker → DB`, with a **second,
  flag-driven path** for Instagram: `gather → enqueue(PendingPost) → llm_worker
  → LLM decide → Event/Approval`.
- Existing capability flags: `PERMANENT`, `DECIDE_BEFORE_INSERT`, `CHANGE_PROBE`
  (read via `getattr` strings).
- Monoliths to split: `app/services/actions.py` (540 lines), `app/services/llm.py`
  (530), `app/ingest.py` (318), `app/gatherers/hikerapi/gatherer.py` (381).
- Existing queue-ish tables already present: `PendingPost`, `Approval`,
  `EventConflict`.

## 2. Guiding principles

1. **One layer per folder; one contract per boundary.** Every module belongs to
   exactly one category and talks to others only through that category's
   interface.
2. **Dependencies flow one way** (down the layers); no cycles.
3. **DB is the bus *between* loops; inline calls *within* a loop.** Sync work =
   direct function calls; async handoff = a `queue_*` row the next loop polls.
4. **Standard interfaces make internals swappable** (`Gatherer`,
   `DecideStrategy`, `PeriodicWorker`, the `application` facade, the storage
   seam).
5. **Incremental migration, tests green at every step.** Behavior-identical until
   the additive dedupe split and the schema rename.
6. **Shims during moves; remove internal shims at the end.** No `python -m app.X`
   leakage — the CLI is the only operator surface.

## 3. Mental model: loops + DB-as-bus + three surfaces

Three *kinds* of processes, only one of which is a "loop":

1. **Loops** (`workers/`) — `PeriodicWorker` subclasses that poll `queue_*` tables
   forever.
2. **Servers** (`servers/`) — long-running HTTP processes. The `engine` server
   *hosts* the loops (starts the workers).
3. **CLI** (`cli.py`) — one-shot commands that parse args, run, and exit
   (`ripcale ingest`, `ripcale backup`, …).

**Trigger model:** a loop's output (a status change or a new row) is the trigger
for the next loop, which notices it on its next poll. This is *polling*, not
push — fine at hour-scale cadence; not instant.

```
intake.yaml sources → Ingest loop → Event rows + queue_post(pending)
queue_post        → Ingestion-LLM loop (transcribe → decide → apply) → Event / queue_approval
Events            → Dedupe-detect loop → queue_dedup(pending)
queue_dedup       → Dedupe-decide loop (LLM decide_pair) → queue_approval(event_merge)
queue_approval    → Approval loop (Telegram, future) → apply merge → Events
queue_conflict    → Reconciliation (human now → LLM later) → apply/syncretize → Events
time              → Backup loop
```

## 4. Naming conventions (locked)

- **Work-queue tables**: prefix **`queue_`** + noun describing the work; every
  queue table has a **`status` column** with a documented state machine.

| Table | Consumed by | Status states |
|---|---|---|
| `queue_post` (was `PendingPost`) | ingestion-LLM | `pending → processing → created/modified/ignored/failed` |
| `queue_dedup` (new) | dedupe-decide | `pending → decided/done/skipped` |
| `queue_approval` (was `Approval`) | approval (Telegram) | `pending → approved/rejected` |
| `queue_conflict` (was `EventConflict`) | reconciliation | `pending → resolved` |

- **Servers**: `public` (read-only) and **`engine`** (R/W — powers
  ingest/decide/write, owns the embedded SQLite DB, hosts the workers).
- **DB module** that holds the SQLAlchemy engine: **`db/connection.py`** (NOT
  `db/engine.py`), so "engine" means only the server.
- **Auth stays "admin"**: the privileged *user* (`admin_username`,
  `admin_password_hash`, `ensure_admin_user()`) is an auth concept, separate from
  the server rename. The `/debug/*` routes stay `/debug`.
- **CLI**: single `ripcale` command, subcommands via argparse.

Implied by the above (confirm during migration): `admin_host`/`admin_port` →
`engine_host`/`engine_port`; compose service `admin` → `engine`.

## 5. Standard interfaces (the seams)

```python
# gatherers/base.py — Gatherer is a small CLASS + typing.Protocol (typed, validated)
class Gatherer(Protocol):
    CONTRACT_VERSION: int
    def run(self, source: SourceConfig) -> GathererResult: ...
    # optional capabilities, read via the Protocol (not getattr strings):
    PERMANENT: bool
    DECIDE_BEFORE_INSERT: bool
    CHANGE_PROBE: bool
    def probe(self, source, previous_state: dict | None) -> dict: ...
```

```python
# pipeline/decide_strategy.py — how a source's events get persisted (fixes the fork)
class DecideStrategy(Protocol):
    def run(self, session, source, run_fn, *, dry_run: bool) -> dict: ...
class InsertStrategy: ...        # normal: decisionmaker → Event
class EnqueueStrategy: ...       # LLM: pending → worker
class ProbeEnqueueStrategy: ...  # change-probe short-circuit (F21.05)
# registry.strategy_for(gatherer) -> DecideStrategy; ingest never branches on flags
```

```python
# workers/base.py — PeriodicWorker is an ABC (shared loop behavior)
class PeriodicWorker(ABC):
    name: str
    def __init__(self, interval_seconds: int): ...
    def start(self) -> None: ...       # idempotent daemon thread (shared)
    def run_once(self) -> dict: ...    # one tick (subclass implements)
    def status(self) -> dict: ...      # {enabled, running, last_run_at, …} (shared)
    def _reason(self) -> str | None: ...  # gate
```

```python
# db/migrations.py — declarative column list (replaces hand-rolled if/else)
MIGRATIONS: list[tuple[str, str, str]] = [
    ("source", "probe_state", "VARCHAR"),
    # one line per new column going forward
]
```

```python
# application/ — the request-agnostic facade (plain functions, ActionError on bad input)
# one module per feature; __init__.py re-exports; routers + future Telegram both call this
```

## 6. Target filesystem structure

```
app/
├── core/                # shared vocabulary: config, intake, schema, identity, timeutil, serializers
├── db/                  # storage: connection.py, models.py, migrations.py, session.py
├── gatherers/           # base.py (Protocol+fetch+SourceIssue), errors.py, elfsight/, ics/, hikerapi/
├── pipeline/            # registry.py, ingest.py, categorize.py, sieve.py, decisionmaker.py, decide_strategy.py
├── llm/                 # pending.py, transcribe.py, context.py, decide.py, apply.py
├── moderation/          # approvals.py, overseer.py, conflicts.py
├── workers/             # base.py, scheduler.py, ingest_llm.py, dedupe_detect.py, dedupe_decide.py, backup.py
├── services/            # events, archive, expiry, recurrence, placeholders, categories, stats, status,
│                        # images, ics, auth, deepseek, ssrf, clock, lock, retag, wipe, coherence, testrunner
├── application/         # __init__.py + ingest, events, backups, approvals, conflicts, overseer, llm, retag, wipe, pipeline, overview
├── servers/             # public.py, engine.py, both.py, __init__.py(start)
├── routers/             # thin HTTP handlers
├── cli.py               # the ripcale command
├── logging.py  security.py  web.py
```

Dependency direction: `cli → servers → {workers, routers} → application →
{pipeline, llm, moderation, services} → db → core`, with `gatherers` consumed by
`pipeline`, `core` at the bottom.

## 7. The loops (inventory)

| Loop (`workers/`) | Polls / trigger | Produces |
|---|---|---|
| `scheduler` | time (`ingest_interval_minutes`) | drives the pipeline; Events; `queue_post` |
| `ingest_llm` | `queue_post(pending)` | transcribe → decide → apply → Event / `queue_approval` |
| `dedupe_detect` | Events (scan) | `queue_dedup(pending)` — **no LLM** |
| `dedupe_decide` | `queue_dedup(pending)` | LLM `decide_pair` → `queue_approval(event_merge)` |
| `backup` | time (`backup_interval_hours`) | snapshot |
| *(future)* `approval` (Telegram, F36) | `queue_approval(pending)` | apply merge → Events |
| *(future)* reconciliation | `queue_conflict(pending)` | human now, LLM later → Events |

**Transcribe + decide are one loop, two stages** (`llm/transcribe.py`,
`llm/decide.py`, `llm/apply.py` wired by `workers/ingest_llm.py`): decide needs
the transcription of the same post, there is no independent consumer, and no
separate cadence — so they share one queue entry, not two loops.

## 8. The CLI (`ripcale`)

`[project.scripts] ripcale = "app.cli:main"` in `pyproject.toml`;
`app/cli.py` is argparse subparsers dispatching to plain functions.

```python
def main() -> int:
    p = argparse.ArgumentParser(prog="ripcale")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start"); s.add_argument("target", choices=["public", "engine", "both"])
    i = sub.add_parser("ingest"); i.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("backup"); b.add_argument("action", choices=["run","list","prune","restore"])
    b.add_argument("name", nargs="?"); b.add_argument("--yes", action="store_true")
    # auth, debug, archive, images, audit — same pattern
    args = p.parse_args(); return dispatch(args)
```

Subcommands: `ripcale start public|engine|both`, `ripcale ingest [--dry-run]`,
`ripcale backup run|list|prune|restore <name> --yes`, `ripcale auth …`,
`ripcale debug …`, `ripcale archive [--commit]`, `ripcale images prune
[--commit]`, `ripcale audit`.

`start` hops: `servers/__init__.py::start(target)` →
`servers/{public,engine,both}.py::main()`. `engine.main()` does
`setup_logging(); init_db(); ensure_admin_user(); for w in workers: w.start();
app.start(...)`. Dockerfile `CMD` / compose `command:` become `ripcale start
public` / `ripcale start engine`.

## 9. Redundancy inventory (what we remove / prevent)

1. 4× worker scaffold → `PeriodicWorker` ABC.
2. `getattr` capability strings → `Gatherer` Protocol (typed attributes).
3. Hand-rolled `_migrate()` if/else → declarative `MIGRATIONS` list.
4. `actions.py` grows per feature → `application/*` per feature.
5. `ingest.py` summary shapes diverge → `DecideStrategy` (uniform `run()`).
6. `llm.py` mixes context/prompt/apply → `llm/{context,decide,apply,transcribe}`.
7. `if gatherer_decide_before_insert()` branching → strategy dispatch (future
   "modes" = new strategy, no `ingest.py` edit).
8. Entry points flat in `app/` → `servers/` + `cli.py`.

## 10. Migration plan (phases = commits; each ends green)

Order is strict: **F69 → F76**, each phase ends with `pytest` green (542 today).

- **F69 — Phase 0: baseline + persist spec.** Record import graph + test count;
  this document.
- **F70 — Phase 1: extract the seams (no moves).**
  - declarative `db/migrations.py`; `workers/base.py` `PeriodicWorker` + refactor
    the 4 workers; `gatherers/base.py` `Gatherer` Protocol; add `queue_dedup`.
- **F71 — Phase 2: pipeline strategy (the structural fix).**
  - `pipeline/decide_strategy.py` + 3 strategies, move bodies out of `ingest.py`,
    `_run_locked` → dispatch; split `ingest.py` → `pipeline/ingest.py` + CLI;
    shim.
- **F72 — Phase 3: split the monoliths.**
  - `llm/` package (from `llm.py` + `pending.py`); `workers/ingest_llm.py`;
    `application/*` (from `actions.py`); shims.
- **F73 — Phase 4: dedupe split (additive).**
  - `workers/dedupe_detect.py` materializes `queue_dedup`;
    `workers/dedupe_decide.py` (LLM) → `queue_approval`.
- **F74 — Phase 5: hierarchy + queue renames.**
  - `db/` (`connection.py`), `core/`, `moderation/`, `servers/` + `cli.py` +
    `[project.scripts]`; rename tables → `queue_post`/`queue_approval`/
    `queue_conflict`; rename `admin` server → `engine` (keep auth "admin").
- **F75 — Phase 6: gatherer classes + Protocol.**
  - convert each gatherer module → small class; `registry` returns instances;
    `strategy_for` uses the object; capabilities as typed class attributes.
- **F76 — Phase 7: docs, contract, shim sweep, verification.**
  - rewrite `AGENTS.md` architecture; update contract docs / `DEVLOG.md` /
    `README.md`; remove internal shims; full suite + `ripcale` smoke + `docker
    compose up --build` + live ingest.

## 11. Before/after map (compact)

| Current | Target | Type |
|---|---|---|
| `app/ingest.py` | `pipeline/ingest.py` + CLI | split |
| `app/registry.py` | `pipeline/registry.py` | move |
| `app/models.py` · `app/db.py` | `db/{models,connection,migrations,session}.py` | move |
| `config/schema/identity/timeutil/serializers/intake.py` | `core/` | move |
| `services/llm.py` · `services/pending.py` | `llm/{decide,apply,context,transcribe,pending}.py` | split/move |
| `services/{scheduler,llm_worker,overseer_worker,backup_worker}.py` | `workers/{scheduler,ingest_llm,dedupe_decide,backup}.py` (+`base.py`) | move |
| `services/actions.py` | `application/*` | split |
| `services/{approvals,overseer,conflicts}.py` | `moderation/` | move |
| `main/public/admin/archive/auth/backup/debug/images/audit.py` | `servers/` + `cli.py` | move/retire |
| `PendingPost`/`Approval`/`EventConflict` | `queue_post`/`queue_approval`/`queue_conflict` | rename |
| `admin` (server/port/config) | `engine` | rename |
| — | `workers/dedupe_detect.py`, `pipeline/decide_strategy.py`, `queue_dedup`, `cli.py` | new |

## 12. Deferred / future (existing backlog, unchanged)

F55 LibCal gatherer · F36 Telegram (approval loop) · F19 frontend (rva.rip) · F41
CI/CD · F43 external API contract · F57 Highlight · F16 `/sources` · F56.02
debug tooling · F20 community submission (deferred) · F23.02 done.

## 13. Decisions log (locked)

1. Structural review **now**, before more features.
2. Full modularization, standard interfaces, swappable internals.
3. **DB-as-bus** between loops; inline calls within a loop.
4. **Explicit `queue_*` tables per loop**, `queue_` prefix + `status` column.
5. Dedupe **split** into detect (no LLM) + decide (LLM).
6. `EventConflict` human-on-demand, but via a standard API an LLM can later enter
   identically.
7. Transcribe+decide = **one loop, two stages**.
8. Gatherer = **small class + `typing.Protocol`**; `PeriodicWorker` = **ABC**.
9. Facade = **`application/`** package.
10. **Remove internal shims**; single `ripcale` CLI (no `python -m app.X` leakage).
11. CLI verbs: **`ripcale start public|engine|both`**.
12. R/W server = **`engine`**; DB module = **`db/connection.py`**; auth user stays
    **`admin`**.
13. Migrations = declarative list (not Alembic, for now).
14. Table renames happen **after** the dedupe split (so `queue_dedup` is born with
    the prefix).
