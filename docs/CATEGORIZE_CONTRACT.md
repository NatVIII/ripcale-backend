# Categorize Contract

Version: 5

The contract between the **Categorize** stage (`app/categorize/categorize.py`) and
the rest of the pipeline (Gatherer → Categorize → Sieve → Decisionmaker → storage).
This document is the single source of truth for how categories are *assigned* to
events by config, independent of any gatherer.

## Data flow

```
GathererResult → categorize.apply(source, events) → (events mutated in place)
                                                   → sieve.classify(...)
```

## Signature

```python
categorize.apply(source: SourceConfig, events: list[ScrapedEvent], rules: list[CategoryRule] | None = None) -> None
categorize.resolve_rules(source: SourceConfig) -> list[CategoryRule]
```

`apply` mutates each event's `categories` **in place**, and runs **before** the
sieve hashes, so assigned categories participate in change detection. With
`rules=None` it applies `resolve_rules(source)`; otherwise it applies the given
list (the debug playground uses this to test custom rules).

## Inputs

- `source` — the `SourceConfig` carrying the rules (and `default_categories`).
- `events` — the `list[ScrapedEvent]` produced by the gatherer (no DB access).

## Rule model (`CategoryRule`)

| Field | Type | Meaning |
|---|---|---|
| `mode` | `"regex"` \| `"assign"` | How the rule matches. |
| `fields` | `list[str]` | String fields to inspect (`[]`/`["*"]` = all text fields). |
| `regex` | `str \| None` | Pattern to match (`regex` mode). |
| `categories` | `list[str]` | Categories applied when the rule fires. |

The matchable string fields are exactly:

`uid, title, description, location, url`

## Semantics

Rules are applied in order: global `rules` (applies to every event) first, then
the gatherer's `rules` (if the source's gatherer has any), then the source's
implicit `default_categories` `assign` rule, then `source.rules` in declared
order.

- **`assign`** — unions `categories` into every event unconditionally.
- **`regex`** — `re.search(pattern, value)` across the selected fields; unions
  `categories` only when at least one field matches.

Applied categories are always **sorted + deduped**. `default_categories` is
sugar for an `assign` rule (single engine — no second code path).

## Identity + slug normalization

After all rules run, every category name is **slugified** and **qualified** to
its `class:name` identity:

- `slugify(name)` — lowercase; spaces → dashes; drop non-`[a-z0-9-]`; collapse
  dash runs; trim edge dashes. Empty slugs are dropped.
- `qualify(name)` — `class:name`, where the class is looked up in
  `category_definitions` and defaults to `intake`.

So the DB only ever stores clean `class:name` slugs (e.g. `intake:art`,
`external:workshop`). Classes are fully dynamic; `intake` is the sole default
class for auto-ingested tags.

## Invariants

- **Read-only** — never touches the DB (takes no `session`).
- **Deterministic** — same config + events yield the same categories.
- **Gatherer-neutral** — operates only on `ScrapedEvent` string fields.
- **Single implementation** — all category assignment and slug normalization
  (global rules, gatherer rules, defaults, and source rules) goes through this
  one stage.

## What the Sieve relies on

The sieve receives events whose categories are already final; it does no
category assignment itself (only `default_location`), and hashes them as-is.
