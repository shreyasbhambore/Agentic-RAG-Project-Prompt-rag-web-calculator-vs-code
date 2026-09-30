"""Phase 8 tests for authorized cross-encoder reranking."""

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import Role, User  # noqa: E402
from app.rag.hybrid import HybridResult  # noqa: E402
from app.rag.reranking import rerank_results  # noqa: E402


@dataclass
class FakeCrossEncoder:
    scores: list[float]

    def predict(self, sentence_pairs: list[tuple[str, str]]) -> list[float]:
        self.sentence_pairs = sentence_pairs
        return self.scores


def user(user_id: str, role: Role = Role.USER) -> User:
    return User(id=user_id, username=user_id, password_hash="not-used", role=role)


def candidate(chunk_id: str, user_id: str, text: str) -> HybridResult:
    return HybridResult(
        text=text,
        metadata={"chunk_id": chunk_id, "allowed_user_id": user_id, "book_id": chunk_id.split("_")[0]},
        fused_score=0.01,
        dense_rank=1,
        sparse_rank=None,
    )


def test_reranking_orders_candidates_by_cross_encoder_score() -> None:
    model = FakeCrossEncoder([0.2, 0.9])
    results = rerank_results(
        "what is relevant?",
        [candidate("book1_a", "user1", "less relevant"), candidate("book1_b", "user1", "best")],
        user("user1"),
        model,
        top_k=2,
    )

    assert [result.metadata["chunk_id"] for result in results] == ["book1_b", "book1_a"]
    assert model.sentence_pairs == [
        ("what is relevant?", "less relevant"),
        ("what is relevant?", "best"),
    ]


def test_reranking_filters_unauthorized_candidates_before_scoring() -> None:
    model = FakeCrossEncoder([0.8])
    results = rerank_results(
        "book",
        [candidate("book2_a", "user2", "secret"), candidate("book1_a", "user1", "allowed")],
        user("user1"),
        model,
        top_k=10,
    )

    assert [result.metadata["chunk_id"] for result in results] == ["book1_a"]
    assert model.sentence_pairs == [("book", "allowed")]


def test_admin_can_rerank_all_candidates() -> None:
    results = rerank_results(
        "books",
        [candidate("book1_a", "user1", "one"), candidate("book2_a", "user2", "two")],
        user("admin", Role.ADMIN),
        FakeCrossEncoder([0.1, 0.2]),
        top_k=10,
    )

    assert {result.metadata["book_id"] for result in results} == {"book1", "book2"}


def test_reranking_rejects_invalid_query_limits_and_score_count() -> None:
    with pytest.raises(ValueError, match="query"):
        rerank_results("", [], user("user1"), FakeCrossEncoder([]), top_k=1)
    with pytest.raises(ValueError, match="top_k"):
        rerank_results("query", [], user("user1"), FakeCrossEncoder([]), top_k=0)
    with pytest.raises(ValueError, match="unexpected number"):
        rerank_results(
            "query",
            [candidate("book1_a", "user1", "text")],
            user("user1"),
            FakeCrossEncoder([]),
            top_k=1,
        )
