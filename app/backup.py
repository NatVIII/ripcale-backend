"""Backup CLI — `python -m app.backup [--list | --prune]`.

Writes a snapshot by default (tar.gz of the SQLite DB + intake.yaml); `--list`
shows existing snapshots + worker status; `--prune` applies retention only.
Thin wrapper over `app.services.actions`.
"""
#region: imports
import argparse

from app.logging import setup_logging
from app.services import actions
#endregion


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup the SQLite DB + intake.yaml (tar.gz)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="list existing backups")
    group.add_argument("--prune", action="store_true", help="apply retention only (no new snapshot)")
    args = parser.parse_args()

    setup_logging()

    if args.list:
        data = actions.backups_status()
        worker = data["worker"]
        if worker["reason"]:
            print(f"worker: disabled ({worker['reason']})")
        else:
            print(f"worker: enabled · {worker['runs']} runs · next {worker['next_run_at'] or '—'}")
        for b in data["backups"]:
            print(f"  {b['filename']}  {b['size']:,} bytes  {b['created_at']}")
        return

    if args.prune:
        result = actions.backup_prune()
        print(f"pruned {result['pruned']} backup(s); {len(result['backups'])} remaining")
        return

    result = actions.backup_run()
    if result.get("created"):
        print(f"backup created: {result['filename']} ({result['size']:,} bytes; pruned {result.get('pruned', 0)})")
    else:
        print(f"backup skipped: {result.get('reason', 'unknown')}")


if __name__ == "__main__":
    main()
