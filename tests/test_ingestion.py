"""Phase 4 tests for page-aware chunks and access metadata."""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.chunking import chunk_text  # noqa: E402
from app.rag.ingestion import BookSpec, create_chunks  # noqa: E402


def test_chunk_text_is_overlapping_and_rejects_invalid_configuration() -> None:
    chunks = chunk_text("one two three four five six", chunk_size=12, chunk_overlap=4)

    assert len(chunks) >= 2
    assert "one two" in chunks[0]
    assert chunks[1]


def test_chunks_keep_page_source_and_access_metadata() -> None:
    book = BookSpec(
        book_id="book1",
        book_name="Book 1",
        owner_user_id="user-1-id",
        allowed_user_ids=["user-1-id"],
    )
    chunks = create_chunks(
        pages=[(4, "This is enough text to create a document chunk.")],
        book=book,
        source="book1.pdf",
        chunk_size=80,
        chunk_overlap=10,
    )

    assert len(chunks) == 1
    assert chunks[0].metadata == {
        "book_id": "book1",
        "book_name": "Book 1",
        "owner_user_id": "user-1-id",
        "allowed_user_ids": ["user-1-id"],
        "source": "book1.pdf",
        "page_number": 4,
        "chunk_id": "book1_page4_chunk1",
    }
