"""Pipeline package: the gather -> categorize -> sieve -> decide orchestrator.

- `decide_strategy` — how a source's events get persisted (the `DecideStrategy`
  seam that replaces the old `if gatherer_decide_before_insert()` branching).
- `ingest` — the full-batch orchestrator (`run`/`run_report`).
"""
