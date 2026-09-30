"""Ingest one PDF into an inspectable JSONL chunk artifact for Phase 4."""

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.rag.ingestion import ingest_pdf, resolve_book_spec, write_chunks_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and chunk an access-controlled PDF.")
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--book-name", required=True)
    parser.add_argument("--owner-username", required=True)
    parser.add_argument("--allowed-usernames", required=True, nargs="+")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        book = resolve_book_spec(
            db, args.book_id, args.book_name, args.owner_username, args.allowed_usernames
        )
    chunks = ingest_pdf(args.pdf_path, book)
    output_path = args.output or Path("data/processed") / f"{args.book_id}.jsonl"
    count = write_chunks_jsonl(chunks, output_path)
    print(f"Extracted {count} chunks to {output_path}.")


if __name__ == "__main__":
    main()
