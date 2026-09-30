"""Backend-only role and document access decisions.

This module deliberately has no frontend dependency. Retrieval code must call
``can_access_document`` before a document enters a candidate set.
"""

from collections.abc import Mapping
from typing import Any

from app.models import Role, User


def can_access_document(user: User, document_metadata: Mapping[str, Any]) -> bool:
    """Return whether a user may access one document's metadata and content.

    Administrators can access the managed corpus. Other users must appear in
    ``allowed_user_ids``. Missing or malformed access metadata fails closed.
    """
    if user.role == Role.ADMIN:
        return True

    allowed_user_ids = document_metadata.get("allowed_user_ids")
    return isinstance(allowed_user_ids, list) and user.id in allowed_user_ids
