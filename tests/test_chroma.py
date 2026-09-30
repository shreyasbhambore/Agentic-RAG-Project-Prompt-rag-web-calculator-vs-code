"""Phase 5 tests: Chroma must filter unauthorized records before retrieval."""

from pathlib import Path
import sys

import chromadb

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models import Role, User  # noqa: E402
from app.rag.chroma import get_collection, search_authorized, upsert_chunks  # noqa: E402
from app.rag.ingestion import IngestedChunk  # noqa: E402


def user(user_id: str, role: Role = Role.USER) -> User:
    return User(id=user_id, username=user_id, password_hash="not-used", role=role)


def chunk(book_id: str, allowed_user_id: str, text: str) -> IngestedChunk:
    return IngestedChunk(
        text=text,
        metadata={
            "book_id": book_id,
            "book_name": book_id.title(),
            "owner_user_id": allowed_user_id,
            "allowed_user_ids": [allowed_user_id],
            "source": f"{book_id}.pdf",
            "page_number": 1,
            "chunk_id": f"{book_id}_page1_chunk1",
        },
    )


class RecordingCollection:
    """Minimal collection double that prevents model downloads in upsert tests."""

    def __init__(self) -> None:
        self.payload: dict[str, object] = {}

    def upsert(self, **kwargs: object) -> None:
        self.payload = kwargs


def test_upsert_serializes_one_scalar_access_record_per_allowed_user() -> None:
    collection = RecordingCollection()
    shared_chunk = IngestedChunk(
        text="shared content",
        metadata={
            "book_id": "shared",
            "book_name": "Shared",
            "owner_user_id": "user1",
            "allowed_user_ids": ["user1", "user2"],
            "source": "shared.pdf",
            "page_number": 1,
            "chunk_id": "shared_page1_chunk1",
        },
    )

    assert upsert_chunks(collection, [shared_chunk]) == 2  # type: ignore[arg-type]
    assert collection.payload["ids"] == [
        "shared_page1_chunk1::user::user1",
        "shared_page1_chunk1::user::user2",
    ]
    assert collection.payload["metadatas"][0]["allowed_user_id"] == "user1"  # type: ignore[index]


def test_dense_search_filters_by_authorized_user_before_candidates() -> None:
    client = chromadb.EphemeralClient()
    collection = get_collection(client, embedding_function=None)
    collection.upsert(
        ids=["book1_page1_chunk1::user::user1", "book2_page1_chunk1::user::user2"],
        documents=["alpha content", "beta content"],
        metadatas=[
            {"book_id": "book1", "book_name": "Book1", "owner_user_id": "user1", "source": "book1.pdf", "page_number": 1, "chunk_id": "book1_page1_chunk1", "allowed_user_id": "user1"},
            {"book_id": "book2", "book_name": "Book2", "owner_user_id": "user2", "source": "book2.pdf", "page_number": 1, "chunk_id": "book2_page1_chunk1", "allowed_user_id": "user2"},
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
    )

    user1_results = search_authorized(collection, [0.0, 1.0], user("user1"), top_k=10)
    user2_results = search_authorized(collection, [1.0, 0.0], user("user2"), top_k=10)
    admin_results = search_authorized(collection, [1.0, 0.0], user("admin", Role.ADMIN), top_k=10)

    assert [result.metadata["book_id"] for result in user1_results] == ["book1"]
    assert [result.metadata["book_id"] for result in user2_results] == ["book2"]
    assert {result.metadata["book_id"] for result in admin_results} == {"book1", "book2"}
