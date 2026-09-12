"""Auth CLI.

Usage:
    python -m app.auth hash-password           # prompt for a password, print its argon2 hash
    python -m app.auth hash-password <pw>      # hash the given password (note: visible in shell history)
    python -m app.auth gen-pepper              # print a random 256-bit pepper for .env
"""
#region: imports
import argparse
import getpass
import secrets
import sys

from app.services.auth import hash_password
#endregion


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.auth")
    parser.add_argument("command", choices=["hash-password", "gen-pepper"])
    parser.add_argument("password", nargs="?", default=None, help="optional password (otherwise prompted)")
    args = parser.parse_args()

    if args.command == "hash-password":
        password = args.password if args.password is not None else getpass.getpass("password: ")
        if not password:
            sys.exit("empty password")
        print(hash_password(password))
    elif args.command == "gen-pepper":
        print(secrets.token_hex(32))


if __name__ == "__main__":
    main()
