"""Backward-compat shim — the ingest orchestrator moved to `app.pipeline.ingest`.

Per-source steps and the `DecideStrategy` classes live in
`app.pipeline.decide_strategy`. These re-exports keep `python -m app.ingest` and
existing imports working until the shim sweep (F76).
"""
#region: imports
from app.pipeline.decide_strategy import (  # noqa: F401
    ensure_source as _ensure_source,
    process_source,
    probe_enqueue as _probe_and_enqueue,
)
from app.pipeline.ingest import (  # noqa: F401
    _run,
    _run_locked,
    _write_last_ingest,
    archive_service,
    engine,
    init_db,
    load_gatherer,
    load_sources,
    main,
    run,
    run_report,
)
#endregion


if __name__ == "__main__":
    main()
