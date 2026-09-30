"""Local administrator utilities for resetting account passwords."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.models import User


def reset_user_password(db: Session, username: str, new_password: str) -> bool:
    """Replace a user's password hash; return False if the username is unknown."""
    if not username.strip():
        raise ValueError("Username must not be empty.")
    if not 12 <= len(new_password) <= 128:
        raise ValueError("Password must be between 12 and 128 characters.")

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        return False

    user.password_hash = hash_password(new_password)
    db.commit()
    return True
