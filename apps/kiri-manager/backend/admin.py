"""Create or reset the local administrator out of band."""
import argparse
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from .config import Config
from .storage import Storage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Replace password and revoke existing sessions")
    parser.add_argument("--password-stdin", action="store_true", help="Read one password from a private stdin pipe")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.password_stdin:
            password = sys.stdin.readline(130).rstrip("\r\n")
        else:
            password = getpass.getpass("New password for admin: ")
            if password != getpass.getpass("Confirm password: "):
                parser.exit(1, "Passwords differ.\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "No password configured.\n")
    if not 14 <= len(password) <= 128:
        parser.exit(1, "Use a password of 14 to 128 characters.\n")
    store = Storage(Config.from_env(os.environ).data_dir)
    if not store.set_password(generate_password_hash(password), replace=args.reset):
        parser.exit(1, "Admin already exists. Use --reset to replace the password.\n")
    print("Administrator configured.")


if __name__ == "__main__":
    main()
