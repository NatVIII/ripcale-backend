# Sieve Contract

Version: 4

The contract between the **Sieve** (`app/sieve/sieve.py`) and the rest of the
pipeline (Gatherer → Categorize → Sieve → Decisionmaker → storage). This document
is the single source of truth for the sieve stage's behavior and data shapes.

## Data flow

```
GathererResult → categorize.apply(...) → sieve.classify(session, result) → SieveResult
                                                                          → decisionmaker.apply(...)
```

## Inputs

```python
sieve.classify(session: Session, result: GathererResult, *, now: datetime | None = None) -> SieveResult
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
| `dropped` | `int` | Events removed by the relevance/expiry filter (F13). |

### `ClassifiedEvent`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | `stable_id(source.name, event)`. |
| `content_hash` | `str` | `content_hash(event)` (after categorize). |
| `event` | `ScrapedEvent` | The (categorized) incoming event. |
| `changed_fields` | `list[str]` | Which mutable fields differ (updated events only). |

## Classification rules

For each incoming event the sieve:

1. Runs `_relevance(events, now)` — the F13 relevance/expiry filter. It drops
   events that fully ended more than `settings.expire_past_days` ago (recurring
   series only once their **last occurrence** — start + duration — has passed;
   unbounded/unparseable rules are kept), and events starting more than
   `settings.expire_future_days` ahead. Either bound `None` disables that side.
   Dropped events are counted in `SieveResult.dropped` and never classified.
2. Fills missing/blank `location` with the source's `default_location`, **before**
   computing `content_hash`, so it participates in change detection. (Category
   assignment happens upstream, in the categorize stage.)
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
- **Idempotent** — the same inputs + DB state + `now` always yield the same
  `SieveResult`.
- **Deterministic given `now`** — no randomness, no I/O beyond the given
  `session`; the relevance filter is time-gated by the explicit `now` argument
  (defaults to the current time), so tests can pin it.
- **Only normalizes `default_location`** — every other field passes through
  untouched; the sieve does not rewrite event content (categories are assigned by
  the categorize stage).
- `content_hash` is a stability contract defined once in `app/identity.py`;
  changing its inputs re-flags every stored event as "updated".

## What the Decisionmaker relies on

`apply()` trusts `SieveResult.new` / `updated` for persistence and
`unchanged_ids` for stamping `last_seen_at`. It never re-runs classification.
