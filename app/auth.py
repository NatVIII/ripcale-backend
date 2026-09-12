"""Auth CLI.

Usage:
    python -m app.auth hash-password [<pw>]     # prompt (or hash a literal) — argon2id hash for .env
    python -m app.auth gen-pepper               # random 256-bit pepper for .env
    python -m app.auth add-user <username>      # create a user (prompts for a password)
    python -m app.auth change-password <username>
    python -m app.auth remove-user <username>
    python -m app.auth list-users
    python -m app.auth token create <username> [--label <label>]   # mint an API token (shown once)
    python -m app.auth token list <username>                        # list a user's tokens (hashes only)
    python -m app.auth token revoke <token>                         # revoke a token
"""
#region: imports
import argparse
import getpass
import secrets
import sys

from sqlmodel import Session, select

from app.db import engine
from app.models import User
from app.services import auth
#endregion


def _prompt_password() -> str:
    password = getpass.getpass("password: ")
    if not password:
        sys.exit("empty password")
    return password


def _init_db() -> None:
    from app.db import init_db
    from app.logging import setup_logging

    setup_logging()
    init_db()


def _resolve_user_id(username: str) -> int:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        sys.exit(f"user not found: {username}")
    return user.id


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.auth")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("hash-password", help="print an argon2id hash for .env")
    p.add_argument("password", nargs="?", default=None)

    sub.add_parser("gen-pepper", help="print a random pepper for .env")

    p = sub.add_parser("add-user", help="create a user")
    p.add_argument("username")

    p = sub.add_parser("change-password", help="reset a user's password")
    p.add_argument("username")

    p = sub.add_parser("remove-user", help="delete a user")
    p.add_argument("username")

    sub.add_parser("list-users", help="list usernames")

    p = sub.add_parser("token", help="manage per-user API tokens")
    p.add_argument("token_sub", choices=["create", "list", "revoke"])
    p.add_argument("token_target")
    p.add_argument("--label", default="", help="label for a new token")

    args = parser.parse_args()

    if args.command in {"add-user", "change-password", "remove-user", "list-users", "token"}:
        _init_db()

    if args.command == "hash-password":
        password = args.password if args.password is not None else _prompt_password()
        print(auth.hash_password(password))
    elif args.command == "gen-pepper":
        print(secrets.token_hex(32))
    elif args.command == "add-user":
        print("created" if auth.create_user(args.username, _prompt_password()) else "username already taken")
    elif args.command == "change-password":
        print("updated" if auth.change_password(args.username, _prompt_password()) else "user not found")
    elif args.command == "remove-user":
        print("removed" if auth.remove_user(args.username) else "user not found")
    elif args.command == "list-users":
        for username in auth.list_users():
            print(username)
    elif args.command == "token":
        if args.token_sub == "create":
            token = auth.create_api_token(_resolve_user_id(args.token_target), args.label)
            print(f"token (save it now — shown once): {token}")
        elif args.token_sub == "list":
            for t in auth.list_api_tokens(_resolve_user_id(args.token_target)):
                print(f"{t['token_hash']}…  {t['label']}  {t['created_at']}")
        elif args.token_sub == "revoke":
            print("revoked" if auth.revoke_api_token(args.token_target) else "token not found")


if __name__ == "__main__":
    main()
