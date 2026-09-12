"""Auth CLI.

Usage:
    python -m app.auth hash-password           # prompt for a password, print its argon2 hash
    python -m app.auth hash-password <pw>      # hash the given password (note: visible in shell history)
    python -m app.auth gen-pepper              # print a random 256-bit pepper for .env
    python -m app.auth add-user <username>     # create a user (prompts for a password)
    python -m app.auth change-password <username>
    python -m app.auth remove-user <username>
    python -m app.auth list-users
"""
#region: imports
import argparse
import getpass
import secrets
import sys

from app.services import auth
#endregion


def _prompt_password() -> str:
    password = getpass.getpass("password: ")
    if not password:
        sys.exit("empty password")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.auth")
    parser.add_argument("command", choices=["hash-password", "gen-pepper", "add-user", "change-password", "remove-user", "list-users"])
    parser.add_argument("argument", nargs="?", default=None, help="password (hash-password) or username (user commands)")
    args = parser.parse_args()

    if args.command in {"add-user", "change-password", "remove-user", "list-users"}:
        from app.db import init_db
        from app.logging import setup_logging

        setup_logging()
        init_db()

    if args.command == "hash-password":
        password = args.argument if args.argument is not None else _prompt_password()
        print(auth.hash_password(password))
    elif args.command == "gen-pepper":
        print(secrets.token_hex(32))
    elif args.command == "add-user":
        if not args.argument:
            sys.exit("usage: app.auth add-user <username>")
        created = auth.create_user(args.argument, _prompt_password())
        print("created" if created else "username already taken")
    elif args.command == "change-password":
        if not args.argument:
            sys.exit("usage: app.auth change-password <username>")
        changed = auth.change_password(args.argument, _prompt_password())
        print("updated" if changed else "user not found")
    elif args.command == "remove-user":
        if not args.argument:
            sys.exit("usage: app.auth remove-user <username>")
        removed = auth.remove_user(args.argument)
        print("removed" if removed else "user not found")
    elif args.command == "list-users":
        for username in auth.list_users():
            print(username)


if __name__ == "__main__":
    main()
