"""Ingest orchestrator: gather -> sieve -> decide -> store.

`run()` is the entry point (CLI via `python -m app.ingest`). It iterates the
configured sources, calls each gatherer, classifies against the DB (sieve), and
applies the result (decisionmaker). After a non-dry run it writes a small
report to `data/last_ingest.json` for the debug dashboard.

`process_source()` is the reusable per-source unit, also used by the pipeline
playground (`app/routers/pipeline.py`).
"""
#region: imports
import argparse
import json
import logging
from pathlib import Path
from typing import Callable

from sqlmodel import Session, select

from app.categorize import apply as categorize
from app.config import settings
from app.db import engine, init_db
from app.decisionmaker import apply
from app.identity import stable_id
from app.logging import setup_logging
from app.models import Event, Source, utcnow
from app.registry import load_gatherer, load_sources
from app.schema import CategoryRule, GathererResult, SieveResult, SourceConfig
from app.services import lock
from app.services.images import host_images
from app.services.status import record_run, record_status
from app.services.archive import archive as archive_service
from app.sieve import classify

logger = logging.getLogger(__name__)
#endregion


#region: source registry upsert
def _ensure_source(session: Session, cfg: SourceConfig) -> Source:
    """Return the Source row for `cfg`, creating it on first sight."""
    source = session.exec(select(Source).where(Source.name == cfg.name)).first()
    if source is None:
        source = Source(
            name=cfg.name,
            url=cfg.url,
            gatherer=cfg.gatherer,
            is_public=cfg.is_public,
            default_categories=",".join(cfg.default_categories),
        )
        session.add(source)
        session.flush()
        session.refresh(source)
    return source
#endregion


#region: per-source pipeline
def _archived_ids(session: Session, ids: list[str]) -> set[str]:
    """Ids of already-archived events among `ids` (for skipping image hosting, F59.01)."""
    if not ids:
        return set()
    rows = session.exec(
        select(Event.id).where(Event.id.in_(ids), Event.archived_at.is_not(None))
    ).all()
    return set(rows)


def process_source(
    session: Session,
    cfg: SourceConfig,
    run_fn: Callable[[SourceConfig], GathererResult],
    *,
    dry_run: bool = False,
    rules: list[CategoryRule] | None = None,
) -> tuple[SieveResult, dict | None]:
    """Run one source through gather -> categorize -> sieve -> (decide).

    `rules=None` uses the configured rules; otherwise the given list is applied
    (debug playground). Returns (sieved, report).
    """
    result = run_fn(cfg)                       # gather
    # Host images pre-sieve (stable content_hash), but skip archived events (F59.01).
    ids = [stable_id(result.source.name, e) for e in result.events]
    archived = _archived_ids(session, ids)
    host_images([e for e, i in zip(result.events, ids) if i not in archived])
    categorize(result.source, result.events, rules=rules)   # categorize (assign rules, before hash)
    sieved = classify(session, result)         # sieve (reads DB)

    report = None
    if not dry_run:
        source = _ensure_source(session, cfg)
        report = apply(session, source, sieved)  # decide (writes DB; sets source.last_fetched_at)
        session.add(source)

    return sieved, report
#endregion


#region: reporting
def _print_report(name: str, sieved: SieveResult, report: dict | None) -> None:
    """Human-readable per-source summary to stdout."""
    line = f"{name}: {len(sieved.new)} new, {len(sieved.updated)} updated, {sieved.unchanged} unchanged"
    if report is not None:
        line += f"  -> inserted {report['inserted']}, updated {report['updated']}, removed {report['removed']}"
    print(line)
    for classified in sieved.new:
        print(f"  NEW    {classified.event.title!r}")
    for classified in sieved.updated:
        changed = ", ".join(classified.changed_fields)
        print(f"  UPDATE {classified.event.title!r} — changed: {changed}")


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
                sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
            except Exception as exc:
                logger.exception("source %r failed", cfg.name)
                session.rollback()
                record_status(cfg.name, "error", message=str(exc))
                summaries.append({"name": cfg.name, "status": "error", "message": str(exc)})
                continue

            total = len(sieved.new) + len(sieved.updated) + sieved.unchanged
            record_run(cfg.name, total)
            _print_report(cfg.name, sieved, report)
            results.append(sieved)
            summaries.append(
                {
                    "name": cfg.name,
                    "status": "warning" if total == 0 else "ok",
                    "message": "returned 0 events" if total == 0 else None,
                    "new": len(sieved.new),
                    "updated": len(sieved.updated),
                    "unchanged": sieved.unchanged,
                    "dropped": sieved.dropped,
                    "inserted": report["inserted"] if report else None,
                    "updated_rows": report["updated"] if report else None,
                    "removed": report["removed"] if report else None,
                }
            )
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
