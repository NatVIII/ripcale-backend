# Gatherer Contract

Version: 1

The contract between a **Gatherer** (a gatherer in `app/gatherers/*/gatherer.py`)
and the rest of the pipeline (**Sieve → Decisionmaker → storage → API/ICS**).

A Gatherer's only job is to fetch a source and emit its events in one shared
shape. Everything downstream assumes this shape, so every Gatherer must honor
it. This document is the single source of truth for that shape.

## Data flow

```
SourceConfig → Gatherer.run() → GathererResult → Sieve.classify() → SieveResult
                                               → Decisionmaker.apply() → Event (DB)
```

## Configuration

A Gatherer is configured through a **uniform, stable interface** — the same shape
for every gatherer, so identical configuration always yields identical results.
Bespoke, gatherer-specific settings are the rare exception, not the norm.

### Per-source (`SourceConfig`)

Every source uses the same fields:

| Field | Meaning |
|---|---|
| `name` | Display name (the source's unique identifier). |
| `gatherer` | Which gatherer parses this source (the gatherer key, e.g. `elfsight`). |
| `url` | The data endpoint the gatherer fetches (kept secret). |
| `is_public` | Whether this source is listed publicly. |
| `priority` | Optional per-source override (`None` = inherit the gatherer default). |
| `default_categories` | Tags applied to every event from this source. |

### Per-gatherer defaults (`GathererConfig`)

The `gatherers:` block in `config.yaml` holds defaults keyed by gatherer name —
`priority` today, extensible with more typed fields over time. Gatherer-level
resolution is centralized (e.g. `registry.source_priority`), never duplicated
per gatherer.

### Resolution order

```
source override > gatherer default > 0
```

The `run(source: SourceConfig) -> GathererResult` entrypoint is the only
interface a gatherer exposes. It must be deterministic: the same `SourceConfig`
(and `GathererConfig`) must produce the same `GathererResult`.

## The Gatherer contract

A Gatherer is a gatherer `app/gatherers/<name>/gatherer.py` exposing:

```python
def run(source: SourceConfig) -> GathererResult: ...
```

`GathererResult` carries the source config plus a list of `ScrapedEvent`:

```python
class GathererResult:
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
| `recurrence_id` | `datetime \| None` | optional | On an *override* occurrence: the original `DTSTART` of the occurrence it replaces (naive UTC). Also feeds `stable_id()` so overrides don't collide with the master. |
| `exdates` | `list[datetime]` | optional | On the series master: the cancelled occurrence `DTSTART`s (naive UTC). |
| `categories` | `list[str]` | optional | Tags. |
| `raw` | `dict` | optional | The full original source payload. Never persisted, never hashed — debugging/re-parse only. |

### Conventions (the "same data" rules)

- **Naive-UTC datetimes** everywhere; the IANA zone is kept in `timezone`.
- **`uid` stability** is the backbone of dedup — prefer a source-side unique id.
- **`end_at` is exclusive.**
- **`raw` is never persisted** and never part of `content_hash`.

## Downstream stages

The sieve and decisionmaker are documented in their own contracts:

- `docs/SIEVE_CONTRACT.md` — classification into new/updated/unchanged.
- `docs/DECISIONMAKER_CONTRACT.md` — the `ScrapedEvent` → `Event` field mapping.

A Gatherer's only downstream guarantee: the sieve normalizes **nothing except
`default_categories`**; every other field passes through untouched.

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

**Series & overrides (implemented):**

- Occurrences of a series are linked by `(source_id, uid)`. The master carries
  `rrule`; an *edited* occurrence is a separate `ScrapedEvent` with
  `recurrence_id` = its original `DTSTART`; a *cancelled* occurrence is listed
  in the master's `exdates`.
- Identity: an override's `id` is `sha256(source+uid+recurrence_id)`, so it never
  collides with its master (whose `recurrence_id` is `None`).
- `exdates` participates in `content_hash` + change detection; `recurrence_id`
  is identity-only.

**Planned (not yet implemented):**

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
