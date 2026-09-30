"""Tests for local account creation and role/password updates."""

from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.password import verify_password  # noqa: E402
from app.auth.user_management import set_local_user  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Role, User  # noqa: E402


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_create_user_with_requested_role_and_password(db: Session) -> None:
    assert set_local_user(db, "alice", "alice-new-password", Role.USER) is True
    user = db.query(User).filter_by(username="alice").one()
    assert user.role == Role.USER
    assert verify_password("alice-new-password", user.password_hash)


def test_update_existing_user_role_and_password(db: Session) -> None:
    assert set_local_user(db, "alice", "alice-old-password", Role.USER) is True

    assert set_local_user(db, "alice", "alice-admin-password", Role.ADMIN) is False
    user = db.query(User).filter_by(username="alice").one()
    assert user.role == Role.ADMIN
    assert verify_password("alice-admin-password", user.password_hash)
    assert not verify_password("alice-old-password", user.password_hash)


@pytest.mark.parametrize(
    ("username", "password", "role"),
    [
        ("ab", "valid-password-123", Role.USER),
        ("bad name", "valid-password-123", Role.USER),
        ("alice", "short", Role.USER),
        ("alice", "valid-password-123", "owner"),
    ],
)
def test_reject_invalid_account_settings(
    db: Session,
    username: str,
    password: str,
    role: Role,
) -> None:
    with pytest.raises(ValueError):
        set_local_user(db, username, password, role)
