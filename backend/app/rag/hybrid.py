"""Hybrid retrieval that fuses authorized dense and sparse rankings."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.models import Role, User
from app.rag.bm25 import BM25Index, BM25Result


class DenseResultLike(Protocol):
    """Minimum dense-result shape required by the fusion algorithm."""

    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HybridResult:
    """A deduplicated result with reciprocal-rank-fusion details."""

    text: str
    metadata: dict[str, Any]
    fused_score: float
    dense_rank: int | None
    sparse_rank: int | None


def _is_authorized(metadata: dict[str, Any], user: User) -> bool:
    """Keep the fusion boundary fail-closed for normal users."""
    if user.role == Role.ADMIN:
        return True
    return metadata.get("allowed_user_id") == user.id


def fuse_results(
    dense_results: list[DenseResultLike],
    sparse_results: list[BM25Result],
    user: User,
    top_k: int,
    rrf_k: int = 60,
) -> list[HybridResult]:
    """Fuse two already-authorized rankings with reciprocal rank fusion.

    RRF is used because dense distances and BM25 scores have different scales.
    The chunk ID is the stable identity used to deduplicate a result appearing
    in both rankings.
    """
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be greater than zero.")

    combined: dict[str, dict[str, Any]] = {}
    for rank, result in enumerate(dense_results, start=1):
        chunk_id = result.metadata.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or not _is_authorized(result.metadata, user):
            continue
        entry = combined.setdefault(
            chunk_id,
            {
                "text": result.text,
                "metadata": dict(result.metadata),
                "fused_score": 0.0,
                "dense_rank": None,
                "sparse_rank": None,
            },
        )
        entry["fused_score"] += 1 / (rrf_k + rank)
        entry["dense_rank"] = rank

    for rank, result in enumerate(sparse_results, start=1):
        chunk_id = result.metadata.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id or not _is_authorized(result.metadata, user):
            continue
        entry = combined.setdefault(
            chunk_id,
            {
                "text": result.text,
                "metadata": dict(result.metadata),
                "fused_score": 0.0,
                "dense_rank": None,
                "sparse_rank": None,
            },
        )
        entry["fused_score"] += 1 / (rrf_k + rank)
        entry["sparse_rank"] = rank

    ranked = sorted(
        combined.values(),
        key=lambda entry: (-entry["fused_score"], entry["metadata"]["chunk_id"]),
    )
    return [HybridResult(**entry) for entry in ranked[:top_k]]


def search_hybrid(
    collection: Any,
    query_embedding: list[float],
    bm25_index: BM25Index,
    query: str,
    user: User,
    top_k: int | None = None,
    dense_top_k: int | None = None,
    sparse_top_k: int | None = None,
) -> list[HybridResult]:
    """Run authorized dense and sparse searches, then fuse their rankings."""
    from app.config import get_settings
    from app.rag.chroma import search_authorized

    settings = get_settings()
    result_limit = top_k if top_k is not None else settings.top_k_hybrid
    dense_results = search_authorized(
        collection, query_embedding, user, dense_top_k or settings.top_k_dense
    )
    sparse_results = bm25_index.search(query, user, sparse_top_k or settings.top_k_bm25)
    return fuse_results(
        dense_results,
        sparse_results,
        user,
        result_limit,
        rrf_k=settings.hybrid_rrf_k,
    )
