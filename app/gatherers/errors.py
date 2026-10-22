"""Gatherer error taxonomy.

Gatherers signal *soft* failures (a source that is unreachable, private, or
empty in a way that isn't a code/config bug) by raising `SourceIssue`, which the
ingest orchestrator maps to a `warning` status rather than a hard `error`.
Anything else a gatherer raises is treated as a hard failure.
"""
#region: error
class SourceIssue(Exception):
    """The source itself is problematic (private/not-found/empty), not our fault.

    e.g. an Instagram account that is private (`403`) or deleted (`404`). Ingest
    records these as `warning` so a private account doesn't show as a red error.
    """
#endregion
