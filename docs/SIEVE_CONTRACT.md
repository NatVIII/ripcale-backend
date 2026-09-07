# Sieve Contract

Version: 1

The contract between the **Sieve** (`app/sieve/sieve.py`) and the rest of the
pipeline (Gatherer → Sieve → Decisionmaker → storage). This document is the
single source of truth for the sieve stage's behavior and data shapes.

## Data flow

```
GathererResult → sieve.classify(session, result) → SieveResult
                                                    → decisionmaker.apply(...)
```

## Inputs

```python
sieve.classify(session: Session, result: GathererResult) -> SieveResult
```

`GathererResult` = `{source: SourceConfig, events: list[ScrapedEvent]}` (see
`docs/GATHERER_CONTRACT.md` for the `ScrapedEvent` shape). The sieve reads the DB
through `session` to compare incoming events against stored ones; it never
writes.

## Outputs

### `SieveResult`

| Field | Type | Meaning |
|---|---|---|
| `source` | `SourceConfig` | The source being classified (echoed through). |
| `new` | `list[ClassifiedEvent]` | Events with no stored row for their id. |
| `updated` | `list[ClassifiedEvent]` | Events whose stored row has a different `content_hash`. |
| `unchanged` | `int` | Count of events identical to their stored row. |
| `unchanged_ids` | `list[str]` | Ids of unchanged events (so `apply()` can stamp `last_seen_at`). |

### `ClassifiedEvent`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | `stable_id(source.name, event)`. |
| `content_hash` | `str` | `content_hash(event)` (after default-category merge). |
| `event` | `ScrapedEvent` | The (category-merged) incoming event. |
| `changed_fields` | `list[str]` | Which mutable fields differ (updated events only). |

## Classification rules

For each incoming event the sieve:

1. Runs `_relevance(events)` — pass-through today; future home for drop-past rules.
2. Merges the source's `default_categories` into each event's `categories`
   **before** computing `content_hash`, so defaults participate in change detection.
3. Computes `id = stable_id(source.name, event)` and `content_hash(event)`.
4. Buckets each event:
   - **new** — no stored `Event` has this `id`.
   - **updated** — the stored `Event` exists but has a different `content_hash`;
     `changed_fields` is the subset of mutable fields that differ.
   - **unchanged** — the stored `Event` has the same `content_hash`.

## Mutable fields (`changed_fields`)

The complete set of fields that, when they differ, mark an event **updated**:

`title, description, location, url, images, start_at, end_at, timezone, all_day, rrule, exdates, categories`

## Invariants

- **Read-only** — `classify()` never writes to the DB.
- **Idempotent** — the same inputs + DB state always yield the same `SieveResult`.
- **Deterministic** — no randomness, no I/O beyond the given `session`.
- **Only normalizes `default_categories`** — every other field passes through
  untouched; the sieve does not rewrite event content.
- `content_hash` is a stability contract defined once in `app/identity.py`;
  changing its inputs re-flags every stored event as "updated".

## What the Decisionmaker relies on

`apply()` trusts `SieveResult.new` / `updated` for persistence and
`unchanged_ids` for stamping `last_seen_at`. It never re-runs classification.
