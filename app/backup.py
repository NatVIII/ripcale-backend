"""Backup CLI — `python -m app.backup [--list | --prune | restore <name> --yes]`.

Writes a snapshot by default (tar.gz of the SQLite DB + intake.yaml); `--list`
shows existing snapshots + worker status; `--prune` applies retention only;
`restore <name> --yes` restores a snapshot (safety-net backup first). Thin
wrapper over `app.services.actions`.
"""
#region: imports
import argparse

from app.logging import setup_logging
from app.services import actions
#endregion


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup/restore the SQLite DB + intake.yaml (tar.gz)")
    parser.add_argument("--list", action="store_true", help="list existing backups")
    parser.add_argument("--prune", action="store_true", help="apply retention only (no new snapshot)")
    sub = parser.add_subparsers(dest="command")
    restore_parser = sub.add_parser("restore", help="restore a snapshot (overwrites the live DB)")
    restore_parser.add_argument("filename")
    restore_parser.add_argument("--yes", action="store_true", help="confirm the destructive restore")
    args = parser.parse_args()

    setup_logging()

    if args.command == "restore":
        if not args.yes:
            print(f"refusing to restore without --yes (would overwrite the live DB): {args.filename}")
            return
        result = actions.backup_restore(args.filename, confirm=True)
        print(
            f"restored: {result['filename']} "
            f"(safety backup: {result.get('safety_backup') or '—'}; restart recommended)"
        )
        return

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
