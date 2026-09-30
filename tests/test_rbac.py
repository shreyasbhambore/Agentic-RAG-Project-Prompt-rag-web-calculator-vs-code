"""Tests for the document authorization boundary required before retrieval."""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth.authorization import can_access_document  # noqa: E402
from app.models import Role, User  # noqa: E402


def make_user(user_id: str, role: Role = Role.USER) -> User:
    return User(id=user_id, username=user_id, password_hash="not-used-in-this-unit-test", role=role)


BOOK_1 = {"book_id": "book1", "allowed_user_ids": ["user1"]}
BOOK_2 = {"book_id": "book2", "allowed_user_ids": ["user2"]}


def test_user1_can_access_only_book1() -> None:
    user1 = make_user("user1")

    assert can_access_document(user1, BOOK_1) is True
    assert can_access_document(user1, BOOK_2) is False


def test_user2_can_access_only_book2() -> None:
    user2 = make_user("user2")

    assert can_access_document(user2, BOOK_2) is True
    assert can_access_document(user2, BOOK_1) is False


def test_admin_can_access_both_books() -> None:
    admin = make_user("admin", Role.ADMIN)

    assert can_access_document(admin, BOOK_1) is True
    assert can_access_document(admin, BOOK_2) is True


def test_missing_access_metadata_fails_closed() -> None:
    assert can_access_document(make_user("user1"), {"book_id": "unknown"}) is False
