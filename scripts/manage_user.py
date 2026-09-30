"""Create or update a local application user with hidden password prompts."""

import argparse
from getpass import getpass
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.user_management import set_local_user  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Role  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update a local Agentic RAG user account."
    )
    parser.add_argument("--username", required=True, help="Account name to create or update")
    parser.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in Role],
        help="Account role: user or admin",
    )
    args = parser.parse_args()

    password = getpass("Password (12-128 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        parser.error("The passwords do not match.")
    if not 12 <= len(password) <= 128:
        parser.error("Password must be between 12 and 128 characters.")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        created = set_local_user(db, args.username, password, Role(args.role))

    action = "Created" if created else "Updated"
    print(f"{action} account {args.username!r} with role {args.role!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
