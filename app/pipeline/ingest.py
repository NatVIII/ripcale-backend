"""Ingest orchestrator: gather -> categorize -> sieve -> decide -> store.

`run()` is the entry point (CLI via `python -m app.ingest`). It iterates the
configured sources and dispatches each through a `DecideStrategy` chosen from the
gatherer's capabilities — insert (normal), enqueue (LLM), or probe-enqueue
(change-probe). After a non-dry run it writes a small report to
`data/last_ingest.json` for the debug dashboard.

The per-source steps live in `app.pipeline.decide_strategy`; `process_source`
there is the reusable insert step used by the pipeline playground.
"""
#region: imports
import argparse
import json
import logging
from pathlib import Path

from sqlmodel import Session

from app.config import settings
from app.db import engine, init_db
from app.gatherers.errors import SourceIssue
from app.logging import sanitize, setup_logging
from app.models import utcnow
from app.pipeline.decide_strategy import (
    ensure_source as _ensure_source,
    probe_enqueue as _probe_and_enqueue,  # noqa: F401 — re-exported for back-compat
    process_source,  # noqa: F401 — re-exported; used by the playground / actions
    strategy_for,
)
from app.registry import load_gatherer, load_sources
from app.schema import SieveResult
from app.services import lock
from app.services.archive import archive as archive_service
from app.services.placeholders import materialize as materialize_placeholders
from app.services.status import record_run, record_status

logger = logging.getLogger(__name__)
#endregion


#region: reporting
def _write_last_ingest(summaries: list[dict], archived: dict | None = None) -> None:
    """Persist the ingest report to `data/last_ingest.json` (wipe-safe)."""
    path = Path(settings.data_dir) / "last_ingest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": utcnow().isoformat() + "Z", "sources": summaries}
    if archived is not None:
        payload["archived"] = archived
    path.write_text(json.dumps(payload, indent=2))
#endregion


#region: entrypoint
def _run(dry_run: bool = False) -> tuple[list[SieveResult], list[dict]]:
    """Run the full pipeline, guarded by the ingest lock (F11).

    Returns a `skipped` summary instead of running if another ingest holds the
    lock (a scheduled run overlapping a manual one, or vice versa).
    """
    if not lock.acquire():
        logger.warning("ingest already running (lock held); skipping")
        skipped = [{"name": "ingest", "status": "skipped", "message": "ingest already running (lock held)"}]
        return [], skipped
    try:
        return _run_locked(dry_run)
    finally:
        lock.release()


def _run_locked(dry_run: bool = False) -> tuple[list[SieveResult], list[dict]]:
    """Run the full pipeline across every configured source (lock already held)."""
    init_db()
    results: list[SieveResult] = []
    summaries: list[dict] = []
    with Session(engine) as session:
        for cfg in load_sources():
            try:
                run_fn = load_gatherer(cfg.gatherer)
                outcome = strategy_for(cfg.gatherer).run(session, cfg, run_fn, dry_run=dry_run)

                if outcome.total is not None:
                    record_run(cfg.name, outcome.total)
                else:
                    record_status(cfg.name, outcome.status, message=outcome.message)
                if outcome.reporter is not None:
                    outcome.reporter()
                if outcome.sieved is not None:
                    results.append(outcome.sieved)
                summaries.append(outcome.summary)

                if cfg.recurrences and not dry_run:
                    source = _ensure_source(session, cfg)
                    materialize_placeholders(session, source, cfg)
            except SourceIssue as exc:
                logger.warning("source %r skipped: %s", cfg.name, exc)
                session.rollback()
                scrubbed = sanitize(str(exc))
                record_status(cfg.name, "warning", message=scrubbed)
                summaries.append({"name": cfg.name, "status": "warning", "message": scrubbed})
                continue
            except Exception as exc:
                logger.exception("source %r failed", cfg.name)
                session.rollback()
                scrubbed = sanitize(str(exc))
                record_status(cfg.name, "error", message=scrubbed)
                summaries.append({"name": cfg.name, "status": "error", "message": scrubbed})
                continue
            if not dry_run:
                session.commit()

    archived = None
    if not dry_run:
        with Session(engine) as session:
            archived = archive_service(session, dry_run=False)
            session.commit()
        _write_last_ingest(summaries, archived)
    return results, summaries


def run(dry_run: bool = False) -> list[SieveResult]:
    """Run the full pipeline; return the per-source sieve results (CLI)."""
    return _run(dry_run)[0]


def run_report(dry_run: bool = False) -> list[dict]:
    """Run the full pipeline; return the per-source summaries (debug page)."""
    return _run(dry_run)[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ripcale ingest pipeline")
    parser.add_argument("--dry-run", action="store_true", help="classify only, do not write")
    args = parser.parse_args()
    setup_logging()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
#endregion
