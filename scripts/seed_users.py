"""Create the initial development accounts without storing their passwords in code."""

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.auth.password import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Role, User  # noqa: E402


def upsert_user(username: str, password: str, role: Role) -> None:
    """Add an account only when that username does not already exist."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
            db.commit()
            print(f"Created {username} ({role.value}).")
        else:
            print(f"Skipped {username}; it already exists.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed initial Agentic RAG users.")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--user1-password", required=True)
    parser.add_argument("--user2-password", required=True)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    upsert_user("admin", args.admin_password, Role.ADMIN)
    upsert_user("user1", args.user1_password, Role.USER)
    upsert_user("user2", args.user2_password, Role.USER)


if __name__ == "__main__":
    main()
