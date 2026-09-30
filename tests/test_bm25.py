"""Phase 6 tests for access-filtered BM25 sparse retrieval."""

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import Role, User  # noqa: E402
from app.rag.bm25 import BM25Index, load_bm25_index, write_bm25_index  # noqa: E402
from app.rag.ingestion import IngestedChunk  # noqa: E402


def user(user_id: str, role: Role = Role.USER) -> User:
    return User(id=user_id, username=user_id, password_hash="not-used", role=role)


def chunk(
    book_id: str, text: str, allowed_user_ids: list[str], chunk_id: str | None = None
) -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata={
            "book_id": book_id,
            "book_name": book_id.title(),
            "owner_user_id": allowed_user_ids[0],
            "allowed_user_ids": allowed_user_ids,
            "source": f"{book_id}.pdf",
            "page_number": 1,
            "chunk_id": chunk_id or f"{book_id}_page1_chunk1",
        },
    )


def test_sparse_search_returns_only_authorized_book_and_admin_can_search_all() -> None:
    index = BM25Index(
        [
            chunk("book1", "rare orchid botanical taxonomy", ["user1"]),
            chunk("book2", "rare orchid coastal ecology", ["user2"]),
        ]
    )

    user1_results = index.search("orchid taxonomy", user("user1"))
    user2_results = index.search("orchid taxonomy", user("user2"))
    admin_results = index.search("orchid", user("admin", Role.ADMIN))

    assert [result.metadata["book_id"] for result in user1_results] == ["book1"]
    assert [result.metadata["book_id"] for result in user2_results] == ["book2"]
    assert {result.metadata["book_id"] for result in admin_results} == {"book1", "book2"}
    assert user1_results[0].score != 0


def test_writer_creates_one_scalar_access_record_per_user(tmp_path: Path) -> None:
    output = tmp_path / "bm25" / "index.jsonl"
    shared = chunk("shared", "shared searchable content", ["user1", "user2"])

    assert write_bm25_index([shared], output) == 2
    index = load_bm25_index(output)

    assert [result.metadata["allowed_user_id"] for result in index.search("searchable", user("user1"))] == [
        "user1"
    ]
    assert [result.metadata["allowed_user_id"] for result in index.search("searchable", user("user2"))] == [
        "user2"
    ]


def test_sparse_search_returns_empty_for_nonmatching_query_or_unknown_user() -> None:
    index = BM25Index([chunk("book1", "botany plants flowers", ["user1"])])

    assert index.search("astronomy", user("user1")) == []
    assert index.search("botany", user("unknown")) == []


def test_sparse_search_rejects_nonpositive_top_k() -> None:
    index = BM25Index([chunk("book1", "botany plants flowers", ["user1"])])

    with pytest.raises(ValueError, match="top_k must be greater than zero"):
        index.search("botany", user("user1"), top_k=0)
