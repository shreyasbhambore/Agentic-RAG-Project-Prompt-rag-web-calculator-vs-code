"""PDF extraction, page-aware chunk creation, and metadata generation."""

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.rag.chunking import chunk_text


@dataclass(frozen=True)
class BookSpec:
    """Book identity and resolved access rules used for every generated chunk."""

    book_id: str
    book_name: str
    owner_user_id: str
    allowed_user_ids: list[str]


@dataclass(frozen=True)
class IngestedChunk:
    """One text chunk and the metadata required by later secure retrieval."""

    text: str
    metadata: dict[str, object]


def load_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract non-empty text from a PDF, retaining its original page number."""
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"PDF file was not found: {pdf_path}")

    reader = PdfReader(str(pdf_path))
    return [
        (page_number, page.extract_text() or "")
        for page_number, page in enumerate(reader.pages, start=1)
    ]


def create_chunks(
    pages: Iterable[tuple[int, str]], book: BookSpec, source: str, chunk_size: int, chunk_overlap: int
) -> list[IngestedChunk]:
    """Turn page text into chunks carrying complete source and access metadata."""
    chunks: list[IngestedChunk] = []
    for page_number, page_text in pages:
        for index, text in enumerate(chunk_text(page_text, chunk_size, chunk_overlap), start=1):
            chunks.append(
                IngestedChunk(
                    text=text,
                    metadata={
                        "book_id": book.book_id,
                        "book_name": book.book_name,
                        "owner_user_id": book.owner_user_id,
                        "allowed_user_ids": book.allowed_user_ids,
                        "source": source,
                        "page_number": page_number,
                        "chunk_id": f"{book.book_id}_page{page_number}_chunk{index}",
                    },
                )
            )
    return chunks


def resolve_book_spec(
    db: Session, book_id: str, book_name: str, owner_username: str, allowed_usernames: list[str]
) -> BookSpec:
    """Resolve usernames once at ingestion time to immutable database user IDs."""
    requested_usernames = list(dict.fromkeys([owner_username, *allowed_usernames]))
    users = db.scalars(select(User).where(User.username.in_(requested_usernames))).all()
    users_by_name = {user.username: user for user in users}
    missing = [username for username in requested_usernames if username not in users_by_name]
    if missing:
        raise ValueError(f"Unknown user accounts: {', '.join(missing)}. Seed or register them first.")

    owner = users_by_name[owner_username]
    return BookSpec(
        book_id=book_id,
        book_name=book_name,
        owner_user_id=owner.id,
        allowed_user_ids=[users_by_name[username].id for username in requested_usernames],
    )


def ingest_pdf(pdf_path: Path, book: BookSpec) -> list[IngestedChunk]:
    """Extract and chunk a PDF using the application's configured chunk settings."""
    settings = get_settings()
    return create_chunks(
        load_pdf_pages(pdf_path), book, pdf_path.name, settings.chunk_size, settings.chunk_overlap
    )


def write_chunks_jsonl(chunks: Iterable[IngestedChunk], output_path: Path) -> int:
    """Write an inspectable intermediate artifact for Phase 4 verification."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps({"text": chunk.text, "metadata": chunk.metadata}) + "\n")
            count += 1
    return count
