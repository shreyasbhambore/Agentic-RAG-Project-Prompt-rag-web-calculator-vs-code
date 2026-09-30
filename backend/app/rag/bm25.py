"""Access-filtered BM25 sparse retrieval."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.models import Role, User
from app.rag.ingestion import IngestedChunk


@dataclass(frozen=True)
class BM25Result:
    """A document returned from the caller's authorized sparse index."""

    text: str
    metadata: dict[str, Any]
    score: float


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def _validate_chunk(chunk: IngestedChunk) -> tuple[str, list[str]]:
    metadata = chunk.metadata
    chunk_id = metadata.get("chunk_id")
    allowed_user_ids = metadata.get("allowed_user_ids")
    required_fields = ("book_id", "book_name", "owner_user_id", "source", "page_number")
    if not isinstance(chunk_id, str) or not chunk_id:
        raise ValueError("Chunk metadata must contain a non-empty chunk_id.")
    if any(field not in metadata for field in required_fields):
        raise ValueError("Chunk metadata is missing required retrieval fields.")
    if not isinstance(allowed_user_ids, list) or not all(
        isinstance(user_id, str) and user_id for user_id in allowed_user_ids
    ):
        raise ValueError("Chunk metadata must contain a list of allowed_user_ids.")
    return chunk_id, list(dict.fromkeys(allowed_user_ids))


def write_bm25_index(chunks: Iterable[IngestedChunk], index_path: Path) -> int:
    """Write one sparse-index record per authorized user; return records written."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = index_path.with_suffix(index_path.suffix + ".tmp")
    count = 0
    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            for chunk in chunks:
                _, allowed_user_ids = _validate_chunk(chunk)
                for user_id in allowed_user_ids:
                    metadata = dict(chunk.metadata)
                    metadata.pop("allowed_user_ids", None)
                    metadata["allowed_user_id"] = user_id
                    file.write(json.dumps({"text": chunk.text, "metadata": metadata}) + "\n")
                    count += 1
        temporary_path.replace(index_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return count


class BM25Index:
    """Hold separate ranked corpora per user and one deduplicated admin corpus."""

    def __init__(self, records: Iterable[IngestedChunk]) -> None:
        by_user: dict[str, list[IngestedChunk]] = defaultdict(list)
        all_records: dict[str, IngestedChunk] = {}
        for record in records:
            chunk_id = record.metadata.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError("BM25 records must contain a non-empty chunk_id.")
            user_id = record.metadata.get("allowed_user_id")
            if user_id is None:
                _, allowed_user_ids = _validate_chunk(record)
                user_records = []
                for allowed_user_id in allowed_user_ids:
                    metadata = dict(record.metadata)
                    metadata.pop("allowed_user_ids", None)
                    metadata["allowed_user_id"] = allowed_user_id
                    user_record = IngestedChunk(text=record.text, metadata=metadata)
                    by_user[allowed_user_id].append(user_record)
                    user_records.append(user_record)
                if user_records:
                    all_records.setdefault(chunk_id, user_records[0])
                continue
            if not isinstance(user_id, str) or not user_id:
                raise ValueError("BM25 index record must contain an allowed_user_id.")
            all_records.setdefault(chunk_id, record)
            by_user[user_id].append(record)

        self._user_indices = {
            user_id: self._build_index(user_records) for user_id, user_records in by_user.items()
        }
        self._admin_index = self._build_index(list(all_records.values()))

    @staticmethod
    def _build_index(
        records: list[IngestedChunk],
    ) -> tuple[BM25Okapi, list[IngestedChunk], list[list[str]]] | None:
        searchable = [(record, _tokens(record.text)) for record in records]
        searchable = [(record, tokens) for record, tokens in searchable if tokens]
        if not searchable:
            return None
        documents, tokenized_corpus = zip(*searchable, strict=True)
        corpus = list(tokenized_corpus)
        return BM25Okapi(corpus), list(documents), corpus

    @classmethod
    def from_jsonl(cls, index_path: Path) -> "BM25Index":
        """Load the generated per-user sparse index from JSONL."""
        records: list[IngestedChunk] = []
        with index_path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSON in BM25 index {index_path} at line {line_number}."
                    ) from error
                if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                    raise ValueError(f"Invalid BM25 index record at line {line_number}.")
                metadata = payload.get("metadata")
                if not isinstance(metadata, dict):
                    raise ValueError(f"Invalid BM25 index metadata at line {line_number}.")
                records.append(IngestedChunk(text=payload["text"], metadata=metadata))
        return cls(records)

    def search(
        self, query: str, user: User, top_k: int | None = None
    ) -> list[BM25Result]:
        """Rank only the corpus built for the authenticated user."""
        limit = top_k if top_k is not None else get_settings().top_k_bm25
        if limit <= 0:
            raise ValueError("top_k must be greater than zero.")

        index = self._admin_index if user.role == Role.ADMIN else self._user_indices.get(user.id)
        query_tokens = _tokens(query)
        if index is None or not query_tokens:
            return []

        model, records, tokenized_corpus = index
        scores = model.get_scores(query_tokens)
        ranked = sorted(
            (
                (float(score), record)
                for score, record, document_tokens in zip(
                    scores, records, tokenized_corpus, strict=True
                )
                if any(token in document_tokens for token in query_tokens)
            ),
            key=lambda result: result[0],
            reverse=True,
        )
        return [
            BM25Result(text=record.text, metadata=record.metadata, score=score)
            for score, record in ranked[:limit]
        ]


def load_bm25_index(index_path: str | Path | None = None) -> BM25Index:
    """Load the configured persistent sparse index."""
    path = Path(index_path or get_settings().bm25_index_path)
    return BM25Index.from_jsonl(path)
