# Decisionmaker Contract

Version: 1

The contract between the **Decisionmaker** (`app/decisionmaker/decisionmaker.py`)
and the rest of the pipeline (Gatherer → Sieve → Decisionmaker → storage). This
document is the single source of truth for the decisionmaker stage's behavior.

## Data flow

```
SieveResult → decisionmaker.apply(session, source, sieved) → Event rows (DB)
                                                             → report (dict)
```

## Signature

```python
decisionmaker.apply(session: Session, source: Source, sieved: SieveResult) -> dict
```

## Inputs

- `session` — a SQLAlchemy `Session` (the transaction owner; `apply()` never commits).
- `source` — the `Source` row this run belongs to (its `id` is stamped onto events).
- `sieved` — the `SieveResult` verdict (see `docs/SIEVE_CONTRACT.md`).

## Output

A report `dict`:

| Key | Meaning |
|---|---|
| `inserted` | New events inserted. |
| `updated` | Existing events updated in place. |
| `unchanged` | Passed through from `sieved.unchanged` (not recomputed). |
| `removed` | Events for this source that were not seen this run (stale). |

## Persistence rules

For each `ClassifiedEvent` in the sieve verdict:

1. **`new`** — insert a fresh `Event` row via the field mapping below.
2. **`updated`** — find the existing row by `id` and copy the mapped fields in
   place (bumping `updated_at`); if the row is missing (defensive), insert instead.
3. **`unchanged_ids`** — stamp `last_seen_at` on those rows only (no field copy).

Afterward the decisionmaker sets `source.last_fetched_at = run_ts` (the same
timestamp used for `last_seen_at`) and detects **stale** events: any `Event` for
this source whose `last_seen_at` is `NULL` or `!= run_ts` was removed at the
source. The count becomes the report's `removed`.

## Field mapping (`ScrapedEvent` → `Event`)

| Event column | Source |
|---|---|
| `id` | `classified.id` (derived: `stable_id(...)`) |
| `source_id` | `source.id` |
| `uid` | `event.uid` |
| `title` | `event.title` |
| `description` | `event.description` |
| `location` | `event.location` |
| `url` | `event.url` |
| `images` | `dump_images(event.images)` (JSON text) |
| `start_at` | `event.start_at` |
| `end_at` | `event.end_at` |
| `timezone` | `event.timezone` |
| `all_day` | `event.all_day` |
| `rrule` | `event.rrule` |
| `recurrence_id` | `event.recurrence_id` |
| `exdates` | `dump_exdates(event.exdates)` (JSON text) |
| `categories` | `",".join(sorted(set(event.categories)))` |
| `content_hash` | `classified.content_hash` (derived) |
| `last_seen_at` | `run_ts` (stamped per run) |

Not set by the decisionmaker: `raw` (discarded), `geo`, `priority`,
`redirect_to_id` (these are unset or handled elsewhere).

## Invariants

- **No commit** — `apply()` writes through the given `session` but never commits;
  the caller (`process_source`) owns the transaction.
- **Deterministic** — given the same `(session, source, sieved)`, `apply()`
  produces the same report and DB writes.
- **Trusts the sieve** — the decisionmaker never re-classifies; `new` means
  genuinely-not-present (it is inserted, not re-checked). Re-running the
  *pipeline* is what yields stable state — the sieve reclassifies existing
  events as `unchanged`, so `apply()` never sees them in `new` twice.
- **Policy is pass-through** today — future cross-source heuristics (dedup,
  manual-over-scraped priority) belong here, in this stage.
