"""ChromaDB persistence with pre-retrieval access filtering."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import get_settings
from app.models import Role, User
from app.rag.ingestion import IngestedChunk


@dataclass(frozen=True)
class DenseResult:
    """A document returned from the authorized dense-search candidate set."""

    text: str
    metadata: dict[str, Any]
    distance: float | None


def get_client(persist_directory: str | Path | None = None) -> chromadb.PersistentClient:
    """Open the configured persistent ChromaDB instance."""
    directory = persist_directory or get_settings().chroma_persist_directory
    return chromadb.PersistentClient(path=str(directory))


def get_collection(client: chromadb.ClientAPI, embedding_function: Any | None = None) -> Collection:
    """Get the single RAG collection, creating it when it does not exist."""
    settings = get_settings()
    return client.get_or_create_collection(
        name=settings.chroma_collection_name, embedding_function=embedding_function
    )


def _records_for_chunk(chunk: IngestedChunk) -> list[tuple[str, str, dict[str, str | int]]]:
    """Create one scalar-metadata Chroma record per permitted user.

    Chroma metadata values must be scalar. Duplicating records by
    ``allowed_user_id`` lets a normal-user query use a database-side filter
    before Chroma forms the candidate set.
    """
    metadata = chunk.metadata
    allowed_user_ids = metadata.get("allowed_user_ids")
    if not isinstance(allowed_user_ids, list) or not all(isinstance(user_id, str) for user_id in allowed_user_ids):
        raise ValueError("Chunk metadata must contain a list of allowed_user_ids.")

    required_keys = ("book_id", "book_name", "owner_user_id", "source", "page_number", "chunk_id")
    if any(key not in metadata for key in required_keys):
        raise ValueError("Chunk metadata is missing required retrieval fields.")

    base_metadata: dict[str, str | int] = {
        "book_id": str(metadata["book_id"]),
        "book_name": str(metadata["book_name"]),
        "owner_user_id": str(metadata["owner_user_id"]),
        "source": str(metadata["source"]),
        "page_number": int(metadata["page_number"]),
        "chunk_id": str(metadata["chunk_id"]),
    }
    return [
        (
            f"{base_metadata['chunk_id']}::user::{user_id}",
            chunk.text,
            {**base_metadata, "allowed_user_id": user_id},
        )
        for user_id in allowed_user_ids
    ]


def upsert_chunks(collection: Collection, chunks: Iterable[IngestedChunk]) -> int:
    """Persist chunks with scalar access metadata and return record count."""
    records = [record for chunk in chunks for record in _records_for_chunk(chunk)]
    if not records:
        return 0
    ids, documents, metadatas = zip(*records, strict=True)
    collection.upsert(ids=list(ids), documents=list(documents), metadatas=list(metadatas))
    return len(records)


def search_authorized(
    collection: Collection, query_embedding: list[float], user: User, top_k: int | None = None
) -> list[DenseResult]:
    """Search only candidates the supplied user is authorized to retrieve.

    Normal users are filtered in the Chroma query itself. This is deliberately
    not a post-retrieval filter. Administrators are allowed to query the full
    managed corpus.
    """
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k or get_settings().top_k_dense,
        where=None if user.role == Role.ADMIN else {"allowed_user_id": user.id},
        include=["documents", "metadatas", "distances"],
    )
    documents = result["documents"][0] or []
    metadatas = result["metadatas"][0] or []
    distances = result["distances"][0] or []
    return [
        DenseResult(text=document, metadata=metadata, distance=distance)
        for document, metadata, distance in zip(documents, metadatas, distances, strict=True)
    ]
