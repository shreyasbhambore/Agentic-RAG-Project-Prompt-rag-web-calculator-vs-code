"""Cross-encoder reranking for authorized hybrid retrieval candidates."""

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from app.config import get_settings
from app.models import Role, User
from app.rag.hybrid import HybridResult


class CrossEncoderLike(Protocol):
    """Minimum model interface required by the reranker."""

    def predict(self, sentence_pairs: Sequence[tuple[str, str]]) -> Sequence[float]:
        ...


@dataclass(frozen=True)
class RerankedResult:
    """A hybrid result ordered by cross-encoder relevance."""

    text: str
    metadata: dict[str, Any]
    rerank_score: float
    fused_score: float
    dense_rank: int | None
    sparse_rank: int | None


def _authorized(result: HybridResult, user: User) -> bool:
    """Fail closed if an unauthorized candidate reaches the reranker."""
    return user.role == Role.ADMIN or result.metadata.get("allowed_user_id") == user.id


def rerank_results(
    query: str,
    candidates: list[HybridResult],
    user: User,
    model: CrossEncoderLike,
    top_k: int,
) -> list[RerankedResult]:
    """Score authorized query-document pairs and return the best candidates."""
    if not query.strip():
        raise ValueError("query must not be empty.")
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")

    authorized_candidates = [
        candidate
        for candidate in candidates
        if _authorized(candidate, user)
        and isinstance(candidate.metadata.get("chunk_id"), str)
    ]
    if not authorized_candidates:
        return []

    scores = model.predict([(query, candidate.text) for candidate in authorized_candidates])
    if len(scores) != len(authorized_candidates):
        raise ValueError("Cross-encoder returned an unexpected number of scores.")

    reranked = [
        RerankedResult(
            text=candidate.text,
            metadata=dict(candidate.metadata),
            rerank_score=float(score),
            fused_score=candidate.fused_score,
            dense_rank=candidate.dense_rank,
            sparse_rank=candidate.sparse_rank,
        )
        for candidate, score in zip(authorized_candidates, scores, strict=True)
    ]
    reranked.sort(
        key=lambda result: (-result.rerank_score, result.metadata["chunk_id"])
    )
    return reranked[:top_k]


class CrossEncoderReranker:
    """Lazy local Sentence Transformers cross-encoder model."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().reranker_model
        self._model: CrossEncoderLike | None = None

    def _get_model(self) -> CrossEncoderLike:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                cache_folder=get_settings().embedding_cache_directory,
            )
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[HybridResult],
        user: User,
        top_k: int | None = None,
    ) -> list[RerankedResult]:
        """Rerank candidates using the configured local cross-encoder."""
        settings = get_settings()
        return rerank_results(
            query,
            candidates,
            user,
            self._get_model(),
            top_k if top_k is not None else settings.top_k_reranked,
        )
