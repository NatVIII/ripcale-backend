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
from pathlib import Path
from typing import Callable

from sqlmodel import Session, select

from app.config import settings
from app.db import engine, init_db
from app.decisionmaker import apply
from app.models import Source, utcnow
from app.registry import load_gatherer, load_sources
from app.schema import GathererResult, SieveResult, SourceConfig
from app.sieve import classify
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
def process_source(
    session: Session,
    cfg: SourceConfig,
    run_fn: Callable[[SourceConfig], GathererResult],
    *,
    dry_run: bool = False,
) -> tuple[SieveResult, dict | None]:
    """Run one source through gather -> sieve -> (decide). Returns (sieved, report)."""
    result = run_fn(cfg)                       # gather
    sieved = classify(session, result)         # sieve (reads DB)

    report = None
    if not dry_run:
        source = _ensure_source(session, cfg)
        report = apply(session, source, sieved)  # decide (writes DB)
        source.last_fetched_at = utcnow()
        session.add(source)

    return sieved, report
#endregion


#region: reporting
def _print_report(name: str, sieved: SieveResult, report: dict | None) -> None:
    """Human-readable per-source summary to stdout."""
    line = f"{name}: {len(sieved.new)} new, {len(sieved.updated)} updated, {sieved.unchanged} unchanged"
    if report is not None:
        line += f"  -> inserted {report['inserted']}, updated {report['updated']}"
    print(line)
    for classified in sieved.new:
        print(f"  NEW    {classified.event.title!r}")
    for classified in sieved.updated:
        changed = ", ".join(classified.changed_fields)
        print(f"  UPDATE {classified.event.title!r} — changed: {changed}")


def _write_last_ingest(summaries: list[dict]) -> None:
    """Persist the ingest report to `data/last_ingest.json` (wipe-safe)."""
    path = Path(settings.data_dir) / "last_ingest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timestamp": utcnow().isoformat() + "Z", "sources": summaries}, indent=2))
#endregion


#region: entrypoint
def run(dry_run: bool = False) -> list[SieveResult]:
    """Run the full pipeline across every configured source."""
    init_db()
    results: list[SieveResult] = []
    summaries: list[dict] = []
    with Session(engine) as session:
        for cfg in load_sources():
            run_fn = load_gatherer(cfg.gatherer)
            sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
            _print_report(cfg.name, sieved, report)
            results.append(sieved)
            summaries.append(
                {
                    "name": cfg.name,
                    "new": len(sieved.new),
                    "updated": len(sieved.updated),
                    "unchanged": sieved.unchanged,
                    "inserted": report["inserted"] if report else None,
                    "updated_rows": report["updated"] if report else None,
                }
            )
            if not dry_run:
                session.commit()
    if not dry_run:
        _write_last_ingest(summaries)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ripcale ingest pipeline")
    parser.add_argument("--dry-run", action="store_true", help="classify only, do not write")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
#endregion
