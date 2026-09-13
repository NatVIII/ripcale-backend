"""Archive (GC) CLI — `python -m app.archive [--commit]`.

Dry-run by default (preview only); pass `--commit` to actually archive. Thin
wrapper over `app.services.actions.archive`.
"""
#region: imports
import argparse

from app.db import init_db
from app.logging import setup_logging
from app.services import actions
#endregion


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive expired + removed events (soft-delete)")
    parser.add_argument("--commit", action="store_true", help="write (default is dry-run)")
    args = parser.parse_args()

    setup_logging()
    init_db()

    dry_run = not args.commit
    result = actions.archive(dry_run=dry_run)
    label = "dry run" if dry_run else "committed"
    print(f"{label}: {result['expired']} expired, {result['removed']} removed archived")
    for p in result["preview"]:
        print(f"  {p['reason']:8} {p['title']!r} ({p['id']})")


if __name__ == "__main__":
    main()
