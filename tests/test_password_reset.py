"""Tests for the local account password reset utility."""

from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.password import verify_password  # noqa: E402
from app.auth.password_reset import reset_user_password  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import User  # noqa: E402


def test_password_reset_updates_only_the_hash(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reset.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            user = User(username="alice", password_hash="old-hash")
            db.add(user)
            db.commit()

            assert reset_user_password(db, "alice", "a-new-unique-password") is True
            db.refresh(user)
            assert user.password_hash != "a-new-unique-password"
            assert verify_password("a-new-unique-password", user.password_hash)
            assert not verify_password("old-password", user.password_hash)
    finally:
        engine.dispose()


def test_password_reset_returns_false_for_unknown_username(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'missing.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            assert reset_user_password(db, "missing-user", "a-new-unique-password") is False
    finally:
        engine.dispose()


def test_password_reset_rejects_invalid_password_length(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            with pytest.raises(ValueError, match="12 and 128"):
                reset_user_password(db, "alice", "too-short")
    finally:
        engine.dispose()
