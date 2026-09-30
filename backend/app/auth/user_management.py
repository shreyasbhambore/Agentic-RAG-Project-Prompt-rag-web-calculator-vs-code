"""Local operator utilities for creating or updating application accounts."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.models import Role, User

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


def set_local_user(
    db: Session,
    username: str,
    password: str,
    role: Role,
) -> bool:
    """Create or update a local account; return True when it was newly created."""
    if not _USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username must be 3-64 characters using only letters, numbers, '_' or '-'."
        )
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must be between 12 and 128 characters.")
    if not isinstance(role, Role):
        raise ValueError("Role must be either 'user' or 'admin'.")

    user = db.scalar(select(User).where(User.username == username))
    created = user is None
    if user is None:
        user = User(username=username, password_hash=hash_password(password), role=role)
        db.add(user)
    else:
        user.password_hash = hash_password(password)
        user.role = role

    db.commit()
    return created
