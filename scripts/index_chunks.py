"""Load Phase 4 JSONL chunks into the persistent, access-filtered ChromaDB collection."""

import argparse
from pathlib import Path
import json
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.chroma import get_client, get_collection, upsert_chunks  # noqa: E402
from app.rag.embeddings import get_embedding_function  # noqa: E402
from app.rag.ingestion import IngestedChunk  # noqa: E402


def load_chunks(paths: list[Path]) -> list[IngestedChunk]:
    chunks: list[IngestedChunk] = []
    for path in paths:
        with path.open(encoding="utf-8") as file:
            for line in file:
                payload = json.loads(line)
                chunks.append(IngestedChunk(text=payload["text"], metadata=payload["metadata"]))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Index access-controlled chunks in ChromaDB.")
    parser.add_argument("paths", nargs="+", type=Path, help="Phase 4 JSONL chunk files")
    args = parser.parse_args()

    collection = get_collection(get_client(), get_embedding_function())
    count = upsert_chunks(collection, load_chunks(args.paths))
    print(f"Upserted {count} access-filtered records into collection '{collection.name}'.")


if __name__ == "__main__":
    main()
