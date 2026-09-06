"""Command-line debug/stats tool.

Usage:
    python -m app.debug            # overview stats
    python -m app.debug sources    # per-source summary
    python -m app.debug events --id <id>   # dump a single event

Reads the DB directly (a local process) — no IP allowlist applies.
"""
#region: imports
import argparse
import json

from sqlmodel import Session

from app.db import engine, init_db
from app.services import stats
#endregion


#region: commands
def _cmd_stats(session: Session) -> None:
    out = stats.overview(session)
    out["last_ingest"] = stats.read_last_ingest()
    print(json.dumps(out, indent=2))


def _cmd_sources(session: Session) -> None:
    print(json.dumps(stats.sources(session), indent=2))


def _cmd_events(session: Session, event_id: str) -> None:
    dump = stats.event_dump(session, event_id)
    if dump is None:
        print(f"no event: {event_id}")
        return
    print(json.dumps(dump, indent=2))
#endregion


#region: entrypoint
def main() -> None:
    parser = argparse.ArgumentParser(description="ripcale debug information")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("stats", help="overview stats (default)")
    sub.add_parser("sources", help="per-source summary")
    p_events = sub.add_parser("events", help="dump a single event")
    p_events.add_argument("--id", required=True, help="event id")

    args = parser.parse_args()
    init_db()
    with Session(engine) as session:
        if args.cmd == "sources":
            _cmd_sources(session)
        elif args.cmd == "events":
            _cmd_events(session, args.id)
        else:
            _cmd_stats(session)


if __name__ == "__main__":
    main()
#endregion
