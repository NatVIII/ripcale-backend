# Gatherer Contract

The contract between a **Gatherer** (a source adapter in `app/sources/*/module.py`)
and the rest of the pipeline (**Sieve → Decisionmaker → storage → API/ICS**).

A Gatherer's only job is to fetch a source and emit its events in one shared
shape. Everything downstream assumes this shape, so every Gatherer must honor
it. This document is the single source of truth for that shape.

## Data flow

```
SourceConfig → Gatherer.run() → ModuleResult → Sieve.classify() → SieveResult
                                               → Decisionmaker.apply() → Event (DB)
```

## The Gatherer contract

A Gatherer is a module `app/sources/<name>/module.py` exposing:

```python
def run(source: SourceConfig) -> ModuleResult: ...
```

`ModuleResult` carries the source config plus a list of `ScrapedEvent`:

```python
class ModuleResult:
    source: SourceConfig
    events: list[ScrapedEvent]
```

### `ScrapedEvent` fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `uid` | `str \| None` | recommended | Stable id from the source. **MUST be stable across fetches** — it drives dedup via `stable_id()`. If absent, the pipeline falls back to `title\|start_at` (weaker: an id-less event whose title/time changes is treated as new). |
| `title` | `str` | **required** | Event name. |
| `description` | `str \| None` | optional | Free text; HTML is allowed (kept as-is; ICS strips it to plain text). |
| `location` | `str \| None` | optional | Human-readable venue. |
| `url` | `str \| None` | optional | Canonical link (ticket/CTA). |
| `images` | `list[ImageRef]` | optional | Ordered image gallery. Each `ImageRef` = `{url, alt, source_url}`. Primary/cover = `images[0]`. |
| `start_at` | `datetime \| None` | recommended | Start time, **naive UTC**. |
| `end_at` | `datetime \| None` | optional | End time, **naive UTC**, **exclusive** (FullCalendar/ICS convention). |
| `timezone` | `str \| None` | optional | IANA zone (e.g. `America/New_York`). Display-only; storage is naive UTC. |
| `all_day` | `bool` | optional | All-day events use date-only semantics. |
| `rrule` | `str \| None` | optional | RFC 5545 recurrence rule (RRULE *value* only — no `RRULE:` prefix, no `DTSTART`). Interpreted relative to `start_at` (the first occurrence) in `timezone`. |
| `categories` | `list[str]` | optional | Tags. |
| `raw` | `dict` | optional | The full original source payload. Never persisted, never hashed — debugging/re-parse only. |

### Conventions (the "same data" rules)

- **Naive-UTC datetimes** everywhere; the IANA zone is kept in `timezone`.
- **`uid` stability** is the backbone of dedup — prefer a source-side unique id.
- **`end_at` is exclusive.**
- **`raw` is never persisted** and never part of `content_hash`.

## What the Sieve adds

`sieve.classify(session, ModuleResult) -> SieveResult` is read-only and idempotent:

1. `_relevance(events)` — future relevance filter (F13; pass-through today).
2. Merges the source's `default_categories` into each event's `categories` (so
   defaults participate in change detection).
3. Computes `stable_id(source.name, event)` and `content_hash(event)`.
4. Buckets each event **new / updated / unchanged** vs the DB; "updated" events
   carry `changed_fields` from the mutable set:
   `title, description, location, url, images, start_at, end_at, timezone, all_day, rrule, categories`.

A Gatherer must not assume the sieve normalizes anything except
`default_categories`; every other field passes through untouched.

## What the Decisionmaker persists

`decisionmaker.apply(session, source, SieveResult)` maps each `ScrapedEvent` to an
`Event` row:

| ScrapedEvent | Event |
|---|---|
| (derived) | `id` = `stable_id(...)` |
| `uid` | `uid` |
| `title` | `title` |
| `description` | `description` |
| `location` | `location` |
| `url` | `url` |
| `images` (list of `ImageRef`) | `images` (JSON text) |
| `start_at` / `end_at` | `start_at` / `end_at` |
| `timezone` | `timezone` |
| `all_day` | `all_day` |
| `rrule` | `rrule` |
| `categories` (list) | `categories` (comma-joined) |
| (derived) | `content_hash` |

Not carried: `raw` (discarded). `Event.geo` exists but has no `ScrapedEvent`
counterpart yet (F30).

## Images

Each event carries an **ordered gallery** of images (`images`), so the frontend
can render a rolling carousel. The **primary/cover image is `images[0]`** — there
is no separate cover field.

Each entry is an `ImageRef`:

| Field | Meaning |
|---|---|
| `url` | Display image location — an external URL today (hotlink), an internal ripcale URL once hosting lands (F18). |
| `alt` | Accessibility text (optional). |
| `source_url` | The original external URL, for provenance (optional; set once hosting stores a copy). |

**Today (external linking only):** a Gatherer sets `url` to the external image
URL (and `alt` when available); `source_url` stays `None`. `images` flows
`Gatherer → ScrapedEvent → Event → JSON extendedProps.images` and
`→ ICS (one ATTACH per image, in order; X-RVA-IMAGE = images[0].url)`.

**Planned (internal hosting, F18):** hosting logic stores a local copy and
rewrites each `url` to an internal path while stashing the origin in
`source_url`. A Gatherer written today stays valid — hosting is a downstream
rewrite, not a Gatherer concern.

## Recurrence

A recurring event is represented as **one** `ScrapedEvent` whose `start_at` is
the *first* occurrence (`DTSTART`) and whose `rrule` generates the rest.

- `rrule` is the RFC 5545 RRULE *value* string (e.g. `FREQ=WEEKLY;BYDAY=MO,WE`),
  without the `RRULE:` prefix and without `DTSTART` (the first occurrence is
  `start_at`).
- The rule is interpreted in the event's `timezone` (IANA). `UNTIL`, when
  present, is UTC to match the naive-UTC `start_at`.
- `rrule` participates in `content_hash` and `_CHANGED_FIELDS` — changing the
  recurrence rule is a real "updated".
- The gatherer is responsible for translating its source's native recurrence
  representation into a valid RRULE. A gatherer with no recurrence leaves it
  `None`.

**Planned (not yet implemented):**

- **Series & overrides** (planned; columns added in F31) — occurrences of a series are linked by
  `(source_id, uid)`. The master carries `rrule`; an *edited* occurrence is a
  separate row with `recurrence_id` = its original `DTSTART`; a *cancelled*
  occurrence is listed in the master's `exdates`. Identity for overrides becomes
  `sha256(source+uid+recurrence_id)`.
- **Expansion** (F12) — turning `rrule` + `exdates` + overrides into concrete
  occurrence instances for serving (server-side) and correct timezone-aware ICS.

## Event relationships (planned)

- **Redirects/symlinks** (F31.01) — an event may carry a `redirect_to_id` pointing
  at a canonical event (for merging duplicates, or manual-over-scraped
  priority). Consumers follow the redirect; the API will expose `redirect_to`.

## Invariants (don't break these)

- Naive-UTC storage; `timezone` holds the IANA name.
- `content_hash` is a stability contract — defined once in `app/identity.py`.
- `uid` must be stable across fetches.
- Secret source URLs live in `config.yaml`; never expose them via events.

## Known gaps (future tickets)

- **`geo`** — `Event.geo` exists but `ScrapedEvent` has no `geo` field. Gatherers
  ought to be able to provide coordinates when the source has them (F30).
- **Default location** — events with a missing/blank `location` have no fallback
  (F32).
