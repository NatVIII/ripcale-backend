"""Per-source decide strategies (F71.01).

The pipeline runs `gather -> categorize -> sieve -> decide` for every source, but
*how* the result is persisted varies by gatherer capability:

- `InsertStrategy` — normal sources: persist via the decisionmaker (Event rows).
- `EnqueueStrategy` — LLM sources: enqueue posts into `PendingPost` for the LLM worker.
- `ProbeEnqueueStrategy` — LLM sources with a change-probe: short-circuit unchanged runs.

`strategy_for(gatherer)` picks one, so the orchestrator never branches on flags.
The per-source step functions (and the `process_source` playground entry point)
live here too, beside the strategies that use them.
"""
#region: imports
import json
from dataclasses import dataclass
from typing import Callable, Protocol

from sqlmodel import Session, select

from app.categorize import apply as categorize
from app.decisionmaker import apply
from app.identity import stable_id
from app.models import Event, Source
from app.registry import gatherer_change_probe, gatherer_decide_before_insert, load_probe
from app.schema import CategoryRule, GathererResult, SieveResult, SourceConfig
from app.services.clock import now as clock_now
from app.services.images import host_images
from app.services.pending import enqueue as enqueue_posts
from app.sieve import classify
#endregion


#region: source registry upsert
def ensure_source(session: Session, cfg: SourceConfig) -> Source:
    """Return the Source row for `cfg`, creating it on first sight."""
    source = session.exec(select(Source).where(Source.name == cfg.name)).first()
    if source is None:
        source = Source(
            name=cfg.name,
            url=cfg.url,
            gatherer=cfg.gatherer,
            is_public=cfg.is_public,
            default_categories=",".join(cfg.default_categories),
            llm_context=cfg.llm_context,
        )
        session.add(source)
        session.flush()
        session.refresh(source)
    else:
        source.llm_context = cfg.llm_context  # live-update the LLM tuning knob (F65)
    return source
#endregion


#region: per-source steps
def archived_ids(session: Session, ids: list[str]) -> set[str]:
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
    (debug playground). Returns (sieved, report). Used by the InsertStrategy and
    the pipeline playground.
    """
    result = run_fn(cfg)                       # gather
    # Host images pre-sieve (stable content_hash), but skip archived events (F59.01).
    ids = [stable_id(result.source.name, e) for e in result.events]
    archived = archived_ids(session, ids)
    host_images(session, [e for e, i in zip(result.events, ids) if i not in archived])
    categorize(result.source, result.events, rules=rules)   # categorize (assign rules, before hash)
    sieved = classify(session, result)         # sieve (reads DB)

    report = None
    if not dry_run:
        source = ensure_source(session, cfg)
        report = apply(session, source, sieved)  # decide (writes DB; sets source.last_fetched_at)
        session.add(source)

    return sieved, report


def enqueue_source(
    session: Session,
    cfg: SourceConfig,
    run_fn: Callable[[SourceConfig], GathererResult],
    *,
    dry_run: bool = False,
) -> dict:
    """Run a decide-before-insert source: gather -> enqueue posts (no Event rows)."""
    result = run_fn(cfg)
    source = ensure_source(session, cfg)
    return enqueue_posts(session, source, result, dry_run=dry_run)


def probe_enqueue(
    session: Session,
    cfg: SourceConfig,
    run_fn: Callable[[SourceConfig], GathererResult],
    probe_fn: Callable,
    *,
    dry_run: bool = False,
) -> dict:
    """Change-probe path (F21.05): short-circuit unchanged runs, else full enqueue.

    `probe_state` is an opaque JSON blob owned by the gatherer (here: the cached
    `user_pk` + newest post `code`), so the strategy never interprets it. On an
    unchanged probe we only re-stamp `last_fetched_at`; otherwise we run the full
    gather + enqueue and store the new state.
    """
    source = ensure_source(session, cfg)
    previous = None
    if source.probe_state:
        try:
            previous = json.loads(source.probe_state)
        except (TypeError, ValueError):
            previous = None

    probe = probe_fn(cfg, previous)
    if not probe["changed"] and not dry_run:
        source.last_fetched_at = clock_now()
        source.probe_state = json.dumps(probe["state"])
        return {"probed": True, "skipped_unchanged": True, "enqueued": 0, "changed": 0, "unchanged": 0}

    result = run_fn(cfg)
    summary = enqueue_posts(session, source, result, dry_run=dry_run)
    if not dry_run:
        source.probe_state = json.dumps(probe["state"])
    return {**summary, "probed": True, "skipped_unchanged": False}
#endregion


#region: reporting
def print_report(name: str, sieved: SieveResult, report: dict | None) -> None:
    """Human-readable insert-path summary to stdout."""
    line = f"{name}: {len(sieved.new)} new, {len(sieved.updated)} updated, {sieved.unchanged} unchanged"
    if report is not None:
        line += f"  -> inserted {report['inserted']}, updated {report['updated']}, removed {report['removed']}"
    print(line)
    for classified in sieved.new:
        print(f"  NEW    {classified.event.title!r}")
    for classified in sieved.updated:
        changed = ", ".join(classified.changed_fields)
        print(f"  UPDATE {classified.event.title!r} — changed: {changed}")


def print_enqueue(name: str, summary: dict) -> None:
    if summary.get("skipped_unchanged"):
        print(f"{name}: unchanged (probe — no new posts)")
        return
    print(
        f"{name}: enqueued {summary['enqueued']}, changed {summary['changed']}, "
        f"unchanged {summary['unchanged']}"
    )
#endregion


#region: strategies
@dataclass
class Outcome:
    """The result of running one source through a strategy."""

    summary: dict                     # exact entry for `last_ingest.json`
    sieved: SieveResult | None = None  # contributes to `run()` results (insert path)
    total: int | None = None          # -> record_run(total); None -> record_status(status, message)
    status: str = "ok"                # used when `total` is None
    message: str | None = None        # used when `total` is None
    reporter: Callable[[], None] | None = None


class DecideStrategy(Protocol):
    def run(
        self,
        session: Session,
        cfg: SourceConfig,
        run_fn: Callable[[SourceConfig], GathererResult],
        *,
        dry_run: bool = False,
    ) -> Outcome: ...


class InsertStrategy:
    """Normal sources: persist via the decisionmaker (Event rows)."""

    def run(self, session, cfg, run_fn, *, dry_run=False) -> Outcome:
        sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
        total = len(sieved.new) + len(sieved.updated) + sieved.unchanged
        summary = {
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
        return Outcome(
            summary=summary,
            sieved=sieved,
            total=total,
            reporter=lambda: print_report(cfg.name, sieved, report),
        )


class EnqueueStrategy:
    """LLM sources: enqueue posts for the LLM worker."""

    def run(self, session, cfg, run_fn, *, dry_run=False) -> Outcome:
        summary = enqueue_source(session, cfg, run_fn, dry_run=dry_run)
        total = summary["enqueued"] + summary["changed"] + summary["unchanged"]
        entry = {
            "name": cfg.name,
            "status": "ok",
            "probed": summary.get("probed", False),
            "skipped_unchanged": summary.get("skipped_unchanged", False),
            "enqueued": summary["enqueued"],
            "changed": summary["changed"],
            "unchanged": summary["unchanged"],
        }
        return Outcome(
            summary=entry,
            total=total,
            reporter=lambda: print_enqueue(cfg.name, summary),
        )


class ProbeEnqueueStrategy:
    """LLM sources with a change-probe: short-circuit unchanged runs."""

    def __init__(self, probe_fn: Callable) -> None:
        self._probe_fn = probe_fn

    def run(self, session, cfg, run_fn, *, dry_run=False) -> Outcome:
        summary = probe_enqueue(session, cfg, run_fn, self._probe_fn, dry_run=dry_run)
        entry = {
            "name": cfg.name,
            "status": "ok",
            "probed": True,
            "skipped_unchanged": summary.get("skipped_unchanged", False),
            "enqueued": summary["enqueued"],
            "changed": summary["changed"],
            "unchanged": summary["unchanged"],
        }
        reporter = lambda: print_enqueue(cfg.name, summary)  # noqa: E731
        if summary.get("skipped_unchanged"):
            return Outcome(
                summary=entry,
                total=None,
                status="ok",
                message="unchanged (no new posts)",
                reporter=reporter,
            )
        total = summary["enqueued"] + summary["changed"] + summary["unchanged"]
        return Outcome(summary=entry, total=total, reporter=reporter)


def strategy_for(gatherer: str) -> DecideStrategy:
    """Pick the decide strategy for a gatherer from its intrinsic capabilities."""
    if not gatherer_decide_before_insert(gatherer):
        return InsertStrategy()
    if gatherer_change_probe(gatherer):
        probe_fn = load_probe(gatherer)
        if probe_fn is not None:
            return ProbeEnqueueStrategy(probe_fn)
    return EnqueueStrategy()
#endregion
