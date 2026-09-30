"""Phase 7 tests for hybrid dense and sparse retrieval."""

from pathlib import Path
import sys
from dataclasses import dataclass

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import Role, User  # noqa: E402
from app.rag.bm25 import BM25Result  # noqa: E402
from app.rag.hybrid import fuse_results  # noqa: E402


@dataclass(frozen=True)
class DenseResult:
    text: str
    metadata: dict[str, str | int]
    distance: float | None


def user(user_id: str, role: Role = Role.USER) -> User:
    return User(id=user_id, username=user_id, password_hash="not-used", role=role)


def metadata(chunk_id: str, user_id: str) -> dict[str, str | int]:
    return {
        "chunk_id": chunk_id,
        "book_id": chunk_id.split("_")[0],
        "allowed_user_id": user_id,
        "page_number": 1,
    }


def test_fusion_deduplicates_and_rewards_results_in_both_rankings() -> None:
    current_user = user("user1")
    dense = [
        DenseResult("dense first", metadata("book1_a", "user1"), 0.1),
        DenseResult("shared content", metadata("book1_shared", "user1"), 0.2),
    ]
    sparse = [
        BM25Result("shared content", metadata("book1_shared", "user1"), 4.0),
        BM25Result("sparse only", metadata("book1_b", "user1"), 3.0),
    ]

    results = fuse_results(dense, sparse, current_user, top_k=3)

    assert [result.metadata["chunk_id"] for result in results] == [
        "book1_shared",
        "book1_a",
        "book1_b",
    ]
    assert results[0].dense_rank == 2
    assert results[0].sparse_rank == 1


def test_fusion_rejects_unauthorized_normal_user_results() -> None:
    results = fuse_results(
        [DenseResult("book2", metadata("book2_a", "user2"), 0.1)],
        [BM25Result("book2", metadata("book2_a", "user2"), 5.0)],
        user("user1"),
        top_k=10,
    )

    assert results == []


def test_fusion_allows_admin_to_combine_all_books() -> None:
    results = fuse_results(
        [DenseResult("book1", metadata("book1_a", "user1"), 0.1)],
        [BM25Result("book2", metadata("book2_a", "user2"), 5.0)],
        user("admin", Role.ADMIN),
        top_k=10,
    )

    assert {result.metadata["book_id"] for result in results} == {"book1", "book2"}


def test_fusion_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="top_k"):
        fuse_results([], [], user("user1"), top_k=0)
    with pytest.raises(ValueError, match="rrf_k"):
        fuse_results([], [], user("user1"), top_k=1, rrf_k=0)
