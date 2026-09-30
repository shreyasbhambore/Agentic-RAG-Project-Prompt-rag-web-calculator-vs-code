"""Interactively reset a local account password without exposing it in shell history."""

import argparse
from getpass import getpass
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.password_reset import reset_user_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactively reset a local Agentic RAG account password."
    )
    parser.add_argument("username", help="Existing account username, e.g. alice")
    args = parser.parse_args()

    new_password = getpass("New password (12-128 characters): ")
    confirmation = getpass("Confirm new password: ")
    if new_password != confirmation:
        parser.error("The passwords do not match.")
    if not 12 <= len(new_password) <= 128:
        parser.error("Password must be between 12 and 128 characters.")

    with SessionLocal() as db:
        updated = reset_user_password(db, args.username, new_password)
    if not updated:
        print(f"No account named {args.username!r} exists.")
        return 1

    print(f"Password reset successfully for {args.username}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
