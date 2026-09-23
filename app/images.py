"""Image GC CLI — `python -m app.images prune [--commit]`.

Dry-run by default (report only); pass `--commit` to actually delete orphaned
image files. Thin wrapper over `app.services.actions.prune_images`.
"""
#region: imports
import argparse

from app.db import init_db
from app.logging import setup_logging
from app.services import actions
#endregion


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune orphaned hosted image files")
    sub = parser.add_subparsers(dest="command", required=True)
    prune_p = sub.add_parser("prune", help="delete images referenced by no live event")
    prune_p.add_argument("--commit", action="store_true", help="write (default is dry-run)")
    args = parser.parse_args()

    setup_logging()
    init_db()

    dry_run = not args.commit
    result = actions.prune_images(dry_run=dry_run)
    label = "dry run" if dry_run else "committed"
    print(
        f"{label}: {result['orphan_count']} orphans ({result['bytes_freed']} bytes) "
        f"of {result['on_disk']} on disk, {result['referenced']} referenced"
    )
    for filename in result["preview"]:
        print(f"  {filename}")


if __name__ == "__main__":
    main()
