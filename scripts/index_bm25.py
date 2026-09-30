"""Build the access-filtered BM25 sparse index from Phase 4 JSONL chunks."""

import argparse
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.rag.ingestion import IngestedChunk  # noqa: E402
from app.rag.bm25 import write_bm25_index  # noqa: E402


def load_chunks(paths: list[Path]) -> list[IngestedChunk]:
    chunks: list[IngestedChunk] = []
    for path in paths:
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON in {path} at line {line_number}.") from error
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise ValueError(f"Invalid chunk record in {path} at line {line_number}.")
                metadata = payload.get("metadata")
                if not isinstance(metadata, dict):
                    raise ValueError(f"Invalid chunk metadata in {path} at line {line_number}.")
                chunks.append(IngestedChunk(text=payload["text"], metadata=metadata))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an access-filtered BM25 index from ingested JSONL chunks."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Phase 4 JSONL chunk files")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(get_settings().bm25_index_path),
        help="Output BM25 JSONL index path (defaults to BM25_INDEX_PATH).",
    )
    args = parser.parse_args()

    count = write_bm25_index(load_chunks(args.paths), args.output)
    print(f"Wrote {count} authorized records to BM25 index '{args.output}'.")


if __name__ == "__main__":
    main()
