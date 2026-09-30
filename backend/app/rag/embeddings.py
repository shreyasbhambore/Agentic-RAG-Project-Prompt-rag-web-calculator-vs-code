"""Configurable local embedding model factory."""

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.config import get_settings


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    """Return the configured local Sentence Transformers embedding function."""
    settings = get_settings()
    return SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model,
        device="cpu",
        cache_folder=settings.embedding_cache_directory,
    )
